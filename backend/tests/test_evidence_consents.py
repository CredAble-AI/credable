from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import DemoAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.evidence_consent_repository import SqliteEvidenceConsentRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditActor, AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService


def create_selected_evidence(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> tuple[str, str]:
    created = client.post(
        "/v1/sessions/demo",
        json={"businessBorrowerType": "SOLE_PROPRIETOR"},
    )
    session_id = created.json()["sessionId"]
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    for source_type in (
        ConsentSourceType.BANK_INTERNAL,
        ConsentSourceType.CREDIT_INFORMATION,
    ):
        client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant")
    client.post(f"/v1/sessions/{session_id}/data-sources/refresh")
    client.post(f"/v1/sessions/{session_id}/assessment/run")
    client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")
    selection = client.post(f"/v1/sessions/{session_id}/evidence/next").json()["selection"]
    return session_id, selection["selectionId"]


def endpoint(session_id: str, selection_id: str) -> str:
    return f"/v1/sessions/{session_id}/evidence/selections/{selection_id}/consent"


def test_evidence_consent_exposes_only_selected_scope(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id, selection_id = create_selected_evidence(
        client,
        data_source_service,
        assessment_service,
    )

    response = client.get(endpoint(session_id, selection_id))

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == session_id
    assert body["selectionId"] == selection_id
    assert body["consent"] == {
        "evidenceConsentId": body["consent"]["evidenceConsentId"],
        "selectionId": selection_id,
        "evidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
        "sourceType": "CUSTOMER_SUBMITTED",
        "purposeCode": "SUPPLEMENTAL_CREDIT_ASSESSMENT",
        "purposeDescription": "기존 평가의 불확실성을 확인하기 위한 보완평가에 사용",
        "dataCategories": [
            "BUSINESS_IDENTITY",
            "MONTHLY_SALES",
            "MONTHLY_DEPOSITS",
            "PERIOD_TOTALS",
        ],
        "periodStart": "2026-03-01",
        "periodEnd": "2026-08-31",
        "required": True,
        "status": "PENDING",
        "grantedAt": None,
        "withdrawnAt": None,
        "updatedAt": None,
        "scopeVersion": "demo-recent-revenue-consent-v1",
        "demoOnly": True,
    }
    assert body["consent"]["evidenceConsentId"].startswith("evc_")


def test_grant_is_idempotent_persistent_and_audited_as_customer(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_consent_repository: SqliteEvidenceConsentRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id, selection_id = create_selected_evidence(
        client,
        data_source_service,
        assessment_service,
    )
    route = endpoint(session_id, selection_id)

    first = client.post(f"{route}/grant")
    second = client.post(f"{route}/grant")

    assert first.status_code == 200
    assert second.json() == first.json()
    consent = first.json()["consent"]
    assert consent["status"] == "GRANTED"
    assert consent["grantedAt"] == consent["updatedAt"]

    reopened = SqliteEvidenceConsentRepository(evidence_consent_repository.database_path)
    reopened.initialize()
    stored = reopened.get_for_selection(session_id, selection_id)
    assert stored is not None
    assert stored.model_dump(mode="json", by_alias=True) == consent

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.EVIDENCE_CONSENT_GRANTED
    assert event.actor == AuditActor.CUSTOMER
    assert event.output_summary["selectionId"] == selection_id


def test_withdrawal_and_regrant_preserve_scope_and_history(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id, selection_id = create_selected_evidence(
        client,
        data_source_service,
        assessment_service,
    )
    route = endpoint(session_id, selection_id)
    granted = client.post(f"{route}/grant").json()["consent"]

    withdrawn = client.post(f"{route}/withdraw")
    repeated = client.post(f"{route}/withdraw")
    regranted = client.post(f"{route}/grant")

    assert withdrawn.status_code == 200
    assert withdrawn.json() == repeated.json()
    assert withdrawn.json()["consent"]["status"] == "WITHDRAWN"
    assert regranted.status_code == 200
    assert regranted.json()["consent"]["status"] == "GRANTED"
    assert regranted.json()["consent"]["evidenceConsentId"] == granted["evidenceConsentId"]
    assert regranted.json()["consent"]["scopeVersion"] == granted["scopeVersion"]

    stages = [event.stage for event in session_repository.list_audit_events(session_id)]
    assert stages[-3:] == [
        AuditStage.EVIDENCE_CONSENT_GRANTED,
        AuditStage.EVIDENCE_CONSENT_WITHDRAWN,
        AuditStage.EVIDENCE_CONSENT_GRANTED,
    ]


def test_cross_session_access_and_ungranted_withdrawal_are_blocked(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    owner_session_id, selection_id = create_selected_evidence(
        client,
        data_source_service,
        assessment_service,
    )
    other = client.post(
        "/v1/sessions/demo",
        json={"businessBorrowerType": "CORPORATION"},
    ).json()["sessionId"]

    cross_session = client.get(endpoint(other, selection_id))
    not_granted = client.post(f"{endpoint(owner_session_id, selection_id)}/withdraw")

    assert cross_session.status_code == 404
    assert cross_session.json()["error"]["code"] == "EVIDENCE_SELECTION_NOT_FOUND"
    assert not_granted.status_code == 409
    assert not_granted.json()["error"]["code"] == "EVIDENCE_CONSENT_NOT_GRANTED"
