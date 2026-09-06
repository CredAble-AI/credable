from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import DemoAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.evidence_submission_repository import SqliteEvidenceSubmissionRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService


def create_session(client: TestClient) -> str:
    response = client.post("/v1/sessions/demo", json={"demoProfileId": "small-business"})
    assert response.status_code == 201
    return response.json()["sessionId"]


def prepare_selected_evidence(
    client: TestClient,
    session_id: str,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> dict:
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    for source_type in (
        ConsentSourceType.BANK_INTERNAL,
        ConsentSourceType.CREDIT_INFORMATION,
    ):
        response = client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant")
        assert response.status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/run").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/boundary-check").status_code == 200
    selection_response = client.post(f"/v1/sessions/{session_id}/evidence/next")
    assert selection_response.status_code == 200
    selection = selection_response.json()["selection"]
    assert selection["status"] == "SELECTED"
    return selection


def submission_payload(selection_id: str) -> dict[str, str]:
    return {
        "selectionId": selection_id,
        "submissionMode": "DEMO_FIXTURE_REFERENCE",
    }


def test_submission_is_empty_before_first_submission(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/evidence/submissions/latest")

    assert response.status_code == 200
    assert response.json() == {"sessionId": session_id, "submission": None}


def test_submission_requires_current_selected_evidence(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json=submission_payload("evs_missing"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_SELECTION_NOT_READY"


def test_demo_submission_preserves_metadata_without_raw_evidence(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    selection = prepare_selected_evidence(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json=submission_payload(selection["selectionId"]),
    )

    assert response.status_code == 200
    state = response.json()["submission"]
    assert state["submissionId"].startswith("evd_")
    assert state["selectionId"] == selection["selectionId"]
    assert state["evidenceType"] == "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY"
    assert state["sourceType"] == "CUSTOMER_SUBMITTED"
    assert state["submissionMode"] == "DEMO_FIXTURE_REFERENCE"
    assert state["status"] == "RECEIVED"
    assert state["submittedAt"].endswith("Z")
    assert state["observedAt"] == "2026-08-31T00:00:00Z"
    assert len(state["submissionSnapshotHash"]) == 64
    assert state["dataVersion"] == "demo-recent-revenue-summary-v1"
    assert state["uploadedFile"] is None
    assert state["demoOnly"] is True
    assert "sourceReference" not in response.text
    assert evidence_submission_repository.count_submissions(session_id) == 1

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.EVIDENCE_SUBMITTED
    assert event.input_snapshot_hash == state["submissionSnapshotHash"]
    assert event.data_version == "demo-recent-revenue-summary-v1"
    assert event.policy_version == "demo-novel-evidence-selection-v3"
    assert event.output_summary == {
        "submissionStatus": "RECEIVED",
        "evidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
        "sourceType": "CUSTOMER_SUBMITTED",
        "submissionMode": "DEMO_FIXTURE_REFERENCE",
        "demoOnly": True,
    }

    reopened = SqliteEvidenceSubmissionRepository(evidence_submission_repository.database_path)
    reopened.initialize()
    stored = reopened.get_by_submission_id(state["submissionId"])
    assert stored is not None
    assert stored.model_dump(mode="json", by_alias=True) == state


def test_same_selection_does_not_create_duplicate_submission(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
) -> None:
    session_id = create_session(client)
    selection = prepare_selected_evidence(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    payload = submission_payload(selection["selectionId"])

    first = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json=payload,
    ).json()
    second = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json=payload,
    ).json()
    latest = client.get(f"/v1/sessions/{session_id}/evidence/submissions/latest").json()

    assert second == first
    assert latest == first
    assert evidence_submission_repository.count_submissions(session_id) == 1


def test_submission_mode_is_restricted_to_demo_fixture(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selected_evidence(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": selection["selectionId"],
            "submissionMode": "RAW_FILE_UPLOAD",
        },
    )

    assert response.status_code == 422
