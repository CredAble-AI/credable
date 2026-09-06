import json

from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import DemoAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.evidence_quality_repository import SqliteEvidenceQualityRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.schemas.evidence_quality import EvidenceQualityState
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService
from app.services.evidence_quality_service import (
    DemoEvidenceQualityCatalog,
    EvidenceQualityService,
)


def create_session(client: TestClient) -> str:
    response = client.post("/v1/sessions/demo", json={"demoProfileId": "small-business"})
    assert response.status_code == 201
    return response.json()["sessionId"]


def prepare_submission(
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
    selection_id = selection_response.json()["selection"]["selectionId"]
    submission_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": selection_id,
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    )
    assert submission_response.status_code == 200
    return submission_response.json()["submission"]


def test_quality_is_empty_before_first_check(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )

    response = client.get(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": session_id,
        "quality": None,
        "underwriterReviewId": None,
    }


def test_quality_check_accepts_only_when_every_dimension_passes(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_quality_repository: SqliteEvidenceQualityRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["qualityCheckId"].startswith("evq_")
    assert quality["submissionId"] == submission["submissionId"]
    assert quality["evidenceType"] == "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY"
    assert quality["status"] == "ACCEPTED"
    assert len(quality["checks"]) == 6
    assert {item["status"] for item in quality["checks"]} == {"PASSED"}
    assert quality["rejectionCodes"] == []
    assert quality["suspicionCodes"] == []
    assert quality["eligibleForReassessment"] is True
    assert quality["nextAction"] == "RUN_REASSESSMENT"
    assert quality["underwriterRequired"] is False
    assert quality["checkedAt"].endswith("Z")
    assert quality["submissionSnapshotHash"] == submission["submissionSnapshotHash"]
    assert quality["dataVersion"] == submission["dataVersion"]
    assert quality["qualityPolicyVersion"] == "demo-evidence-quality-policy-v1"
    assert quality["demoOnly"] is True
    assert evidence_quality_repository.count_checks(session_id) == 1

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.EVIDENCE_QUALITY_CHECKED
    assert event.input_version == submission["submissionId"]
    assert event.input_snapshot_hash == submission["submissionSnapshotHash"]
    assert event.data_version == submission["dataVersion"]
    assert event.policy_version == "demo-evidence-quality-policy-v1"
    assert event.output_summary == {
        "qualityStatus": "ACCEPTED",
        "failedCheckCount": 0,
        "suspicionCount": 0,
        "eligibleForReassessment": True,
        "nextAction": "RUN_REASSESSMENT",
        "underwriterRequired": False,
        "evidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
        "demoOnly": True,
    }


def test_quality_check_is_idempotent_for_same_submission(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_quality_repository: SqliteEvidenceQualityRepository,
) -> None:
    session_id = create_session(client)
    submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    endpoint = (
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    first = client.post(endpoint).json()
    second = client.post(endpoint).json()
    stored = client.get(endpoint).json()

    assert second == first
    assert stored == first
    assert evidence_quality_repository.count_checks(session_id) == 1


def test_quality_state_reads_legacy_json_without_routing_fields(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )
    legacy_state = response.json()["quality"]
    legacy_state.pop("suspicionCodes")
    legacy_state.pop("nextAction")
    legacy_state.pop("underwriterRequired")

    restored = EvidenceQualityState.model_validate(legacy_state)

    assert restored.suspicion_codes == []
    assert restored.next_action == "RUN_REASSESSMENT"
    assert restored.underwriter_required is False


def test_quality_check_rejects_failed_or_unverified_dimension(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_quality_service: EvidenceQualityService,
    tmp_path,
) -> None:
    session_id = create_session(client)
    submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    fixture_path = tmp_path / "rejected_quality.json"
    checks = [
        {
            "dimension": dimension,
            "status": status,
            "rationaleCode": rationale,
        }
        for dimension, status, rationale in (
            ("PROVENANCE", "PASSED", "DEMO_SOURCE_REFERENCE_PRESENT"),
            ("FRESHNESS", "FAILED", "DEMO_FRESHNESS_POLICY_FAILED"),
            ("AUTHENTICITY", "NOT_VERIFIED", "DEMO_AUTHENTICITY_NOT_VERIFIED"),
            ("COMPLETENESS", "PASSED", "DEMO_REQUIRED_FIELDS_PRESENT"),
            ("CONSISTENCY", "PASSED", "DEMO_INTERNAL_TOTALS_CONSISTENT"),
            ("MANIPULATION_RISK", "PASSED", "DEMO_MANIPULATION_CHECK_PASSED"),
        )
    ]
    fixture_path.write_text(
        json.dumps(
            {
                "dataVersion": "demo-rejected-quality-v1",
                "qualityPolicyVersion": "demo-rejected-quality-policy-v1",
                "results": [
                    {
                        "evidenceType": submission["evidenceType"],
                        "checks": checks,
                    }
                ],
                "demoOnly": True,
            }
        ),
        encoding="utf-8",
    )
    evidence_quality_service.catalog = DemoEvidenceQualityCatalog(fixture_path)

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["status"] == "REJECTED"
    assert quality["eligibleForReassessment"] is False
    assert quality["suspicionCodes"] == []
    assert quality["nextAction"] == "EXCLUDE_EVIDENCE"
    assert quality["underwriterRequired"] is False
    assert quality["rejectionCodes"] == [
        "DEMO_FRESHNESS_POLICY_FAILED",
        "DEMO_AUTHENTICITY_NOT_VERIFIED",
    ]
    assert quality["qualityPolicyVersion"] == "demo-rejected-quality-policy-v1"


def test_quality_check_hides_submission_from_another_session(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    owner_session_id = create_session(client)
    submission = prepare_submission(
        client,
        owner_session_id,
        data_source_service,
        assessment_service,
    )
    other_session_id = create_session(client)

    response = client.post(
        f"/v1/sessions/{other_session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVIDENCE_SUBMISSION_NOT_FOUND"
