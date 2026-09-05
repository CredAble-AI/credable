import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    DemoAssessmentAdapter,
    DemoSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.assessment_repository import SqliteAssessmentRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService, SupplementalAssessmentService
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
) -> tuple[dict, dict]:
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    for source_type in (
        ConsentSourceType.BANK_INTERNAL,
        ConsentSourceType.CREDIT_INFORMATION,
    ):
        response = client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant")
        assert response.status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200
    baseline_response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    assert baseline_response.status_code == 200
    baseline = baseline_response.json()["assessment"]
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
    return baseline, submission_response.json()["submission"]


def check_quality(client: TestClient, session_id: str, submission_id: str) -> dict:
    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission_id}/quality"
    )
    assert response.status_code == 200
    return response.json()["quality"]


def run_payload(submission_id: str) -> dict[str, str]:
    return {"submissionId": submission_id}


def test_supplemental_assessment_is_empty_before_first_run(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/assessment/supplemental")

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": session_id,
        "supplementalAssessment": None,
    }


def test_supplemental_assessment_requires_quality_check(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    _, submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )

    response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json=run_payload(submission["submissionId"]),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_QUALITY_NOT_READY"


def test_supplemental_assessment_uses_only_accepted_evidence(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    assessment_repository: SqliteAssessmentRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    baseline, submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    quality = check_quality(client, session_id, submission["submissionId"])
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        settings.demo_supplemental_assessments_path
    )

    response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json=run_payload(submission["submissionId"]),
    )

    assert response.status_code == 200
    state = response.json()["supplementalAssessment"]
    assert state["supplementalAssessmentId"].startswith("sam_")
    assert state["baselineAssessmentId"] == baseline["assessmentId"]
    assert state["qualityCheckId"] == quality["qualityCheckId"]
    assert state["submissionId"] == submission["submissionId"]
    assert state["status"] == "COMPLETED"
    assert state["calculatedAt"].endswith("Z")
    assert state["inputSnapshotId"].startswith("sas_")
    assert state["modelVersion"] == "demo-small-business-supplemental-assessment-v1"
    assert state["reasonCode"] is None
    assert state["uncertainty"] == {
        "pointEstimate": None,
        "lowerBound": None,
        "upperBound": None,
        "gradeSet": ["DEMO_GRADE_B"],
        "calibrationMode": "RULE_TABLE",
        "calibrationVersion": "demo-supplemental-uncertainty-rule-table-v1",
        "demoOnly": True,
    }
    assert state["demoOnly"] is True
    assert "sourceReference" not in response.text
    assert client.get(f"/v1/sessions/{session_id}/assessment").json()["assessment"] == baseline
    assert assessment_repository.count_executions(session_id) == 1
    assert assessment_repository.count_supplemental_executions(session_id) == 1

    snapshot = assessment_repository.get_supplemental_snapshot(state["supplementalAssessmentId"])
    assert snapshot is not None
    assert snapshot.baseline_assessment_id == baseline["assessmentId"]
    assert snapshot.baseline_input_snapshot_id == baseline["inputSnapshotId"]
    assert snapshot.baseline_uncertainty.grade_set == ["DEMO_GRADE_B", "DEMO_GRADE_C"]
    assert snapshot.accepted_evidence.quality_check_id == quality["qualityCheckId"]
    assert snapshot.accepted_evidence.submission_id == submission["submissionId"]
    assert (
        snapshot.accepted_evidence.submission_snapshot_hash == submission["submissionSnapshotHash"]
    )
    assert len(snapshot.data_sources) == 4

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.SUPPLEMENTAL_ASSESSMENT_RUN
    assert event.request_id == response.headers["X-Request-ID"]
    assert event.input_version == quality["qualityCheckId"]
    assert event.input_snapshot_hash == state["inputSnapshotId"].removeprefix("sas_")
    assert event.data_version == submission["dataVersion"]
    assert event.model_version == "demo-small-business-supplemental-assessment-v1"
    assert event.policy_version == quality["qualityPolicyVersion"]
    assert event.output_summary == {
        "supplementalAssessmentStatus": "COMPLETED",
        "baselineAssessmentId": baseline["assessmentId"],
        "qualityCheckId": quality["qualityCheckId"],
        "evidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
        "calibrationMode": "RULE_TABLE",
        "calibrationVersion": "demo-supplemental-uncertainty-rule-table-v1",
        "demoOnly": True,
    }


def test_same_quality_check_does_not_create_duplicate_reassessment(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    assessment_repository: SqliteAssessmentRepository,
) -> None:
    session_id = create_session(client)
    _, submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    check_quality(client, session_id, submission["submissionId"])
    endpoint = f"/v1/sessions/{session_id}/assessment/supplemental/run"
    payload = run_payload(submission["submissionId"])

    first = client.post(endpoint, json=payload).json()
    second = client.post(endpoint, json=payload).json()
    latest = client.get(f"/v1/sessions/{session_id}/assessment/supplemental").json()

    assert second == first
    assert latest == first
    assert assessment_repository.count_supplemental_executions(session_id) == 1


def test_rejected_quality_cannot_run_supplemental_assessment(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_quality_service: EvidenceQualityService,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    _, submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    fixture_path = tmp_path / "rejected_quality.json"
    statuses = {
        "PROVENANCE": "PASSED",
        "FRESHNESS": "FAILED",
        "AUTHENTICITY": "PASSED",
        "COMPLETENESS": "PASSED",
        "CONSISTENCY": "PASSED",
        "MANIPULATION_RISK": "PASSED",
    }
    fixture_path.write_text(
        json.dumps(
            {
                "dataVersion": "demo-rejected-quality-v1",
                "qualityPolicyVersion": "demo-rejected-quality-policy-v1",
                "results": [
                    {
                        "evidenceType": submission["evidenceType"],
                        "checks": [
                            {
                                "dimension": dimension,
                                "status": status,
                                "rationaleCode": f"DEMO_{dimension}_{status}",
                            }
                            for dimension, status in statuses.items()
                        ],
                    }
                ],
                "demoOnly": True,
            }
        ),
        encoding="utf-8",
    )
    evidence_quality_service.catalog = DemoEvidenceQualityCatalog(fixture_path)
    quality = check_quality(client, session_id, submission["submissionId"])
    assert quality["status"] == "REJECTED"

    response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json=run_payload(submission["submissionId"]),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_QUALITY_NOT_ACCEPTED"


def test_new_baseline_invalidates_stale_evidence_lineage(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    _, submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    check_quality(client, session_id, submission["submissionId"])
    assert client.post(f"/v1/sessions/{session_id}/assessment/run").status_code == 200

    response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json=run_payload(submission["submissionId"]),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUPPLEMENTAL_ASSESSMENT_LINEAGE_NOT_READY"
