import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    DemoAssessmentAdapter,
    DemoSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.assessment_repository import SqliteAssessmentRepository
from app.repositories.policy_boundary_repository import SqlitePolicyBoundaryRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.assessment import (
    AssessmentUncertainty,
    CalibrationMode,
    SupplementalAssessmentInputSnapshot,
)
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import (
    AssessmentService,
    SupplementalAssessmentService,
    compare_uncertainties,
)
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


def write_cumulative_assessment_catalog(path: Path) -> None:
    def result(grades: list[str], model_version: str) -> dict:
        return {
            "status": "COMPLETED",
            "modelVersion": model_version,
            "uncertainty": {
                "gradeSet": grades,
                "calibrationMode": "RULE_TABLE",
                "calibrationVersion": "demo-uncertainty-rule-table-v1",
                "demoOnly": True,
            },
        }

    path.write_text(
        json.dumps(
            {
                "dataVersion": "test-cumulative-supplemental-v1",
                "assessments": [
                    {
                        "demoProfileId": "small-business",
                        "evidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
                        "result": result(
                            ["DEMO_GRADE_B", "DEMO_GRADE_C"],
                            "test-single-evidence-model-v1",
                        ),
                    },
                    {
                        "demoProfileId": "small-business",
                        "evidenceTypes": [
                            "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
                            "EXTERNAL_CONNECTED_SETTLEMENT_SUMMARY",
                        ],
                        "result": result(
                            ["DEMO_GRADE_B"],
                            "test-cumulative-evidence-model-v1",
                        ),
                    },
                ],
                "demoOnly": True,
            }
        ),
        encoding="utf-8",
    )


def write_accepted_quality_catalog(path: Path, evidence_type: str) -> None:
    dimensions = [
        "PROVENANCE",
        "FRESHNESS",
        "AUTHENTICITY",
        "COMPLETENESS",
        "CONSISTENCY",
        "MANIPULATION_RISK",
    ]
    path.write_text(
        json.dumps(
            {
                "dataVersion": "test-accepted-quality-v1",
                "qualityPolicyVersion": "test-accepted-quality-policy-v1",
                "results": [
                    {
                        "evidenceType": evidence_type,
                        "checks": [
                            {
                                "dimension": dimension,
                                "status": "PASSED",
                                "rationaleCode": f"TEST_{dimension}_PASSED",
                            }
                            for dimension in dimensions
                        ],
                    }
                ],
                "demoOnly": True,
            }
        ),
        encoding="utf-8",
    )


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
    assert state["acceptedEvidenceCount"] == 1
    assert state["uncertainty"] == {
        "pointEstimate": None,
        "lowerBound": None,
        "upperBound": None,
        "gradeSet": ["DEMO_GRADE_B"],
        "calibrationMode": "RULE_TABLE",
        "calibrationVersion": "demo-uncertainty-rule-table-v1",
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
    assert snapshot.accepted_evidence_set == [snapshot.accepted_evidence]
    assert (
        snapshot.accepted_evidence.submission_snapshot_hash == submission["submissionSnapshotHash"]
    )
    assert len(snapshot.data_sources) == 4

    legacy_snapshot = snapshot.model_dump(mode="json", by_alias=True)
    legacy_snapshot.pop("acceptedEvidenceSet")
    restored = SupplementalAssessmentInputSnapshot.model_validate(legacy_snapshot)
    assert restored.accepted_evidence_set == [restored.accepted_evidence]

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
        "acceptedEvidenceCount": 1,
        "calibrationMode": "RULE_TABLE",
        "calibrationVersion": "demo-uncertainty-rule-table-v1",
        "demoOnly": True,
    }


def test_repeated_assessment_uses_all_accepted_evidence_cumulatively(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    evidence_quality_service: EvidenceQualityService,
    assessment_repository: SqliteAssessmentRepository,
    session_repository: SqliteCustomerSessionRepository,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    _, first_submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    first_quality = check_quality(client, session_id, first_submission["submissionId"])
    supplemental_catalog_path = tmp_path / "cumulative-supplemental.json"
    write_cumulative_assessment_catalog(supplemental_catalog_path)
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        supplemental_catalog_path
    )

    first_assessment_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json=run_payload(first_submission["submissionId"]),
    )
    assert first_assessment_response.status_code == 200
    assert first_assessment_response.json()["supplementalAssessment"]["acceptedEvidenceCount"] == 1
    assert client.post(f"/v1/sessions/{session_id}/assessment/comparison").status_code == 200
    first_resolution_response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")
    assert first_resolution_response.status_code == 200
    assert first_resolution_response.json()["resolution"]["status"] == ("MORE_EVIDENCE_REQUIRED")

    second_selection_response = client.post(f"/v1/sessions/{session_id}/evidence/next")
    assert second_selection_response.status_code == 200
    second_selection = second_selection_response.json()["selection"]
    assert second_selection["iteration"] == 2
    assert second_selection["selectedEvidence"]["evidenceType"] == (
        "EXTERNAL_CONNECTED_SETTLEMENT_SUMMARY"
    )
    second_submission_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": second_selection["selectionId"],
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    )
    assert second_submission_response.status_code == 200
    second_submission = second_submission_response.json()["submission"]

    quality_catalog_path = tmp_path / "accepted-external-quality.json"
    write_accepted_quality_catalog(
        quality_catalog_path,
        second_submission["evidenceType"],
    )
    evidence_quality_service.catalog = DemoEvidenceQualityCatalog(quality_catalog_path)
    second_quality = check_quality(client, session_id, second_submission["submissionId"])
    assert second_quality["status"] == "ACCEPTED"

    second_assessment_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json=run_payload(second_submission["submissionId"]),
    )

    assert second_assessment_response.status_code == 200
    second_assessment = second_assessment_response.json()["supplementalAssessment"]
    assert second_assessment["acceptedEvidenceCount"] == 2
    assert second_assessment["modelVersion"] == "test-cumulative-evidence-model-v1"
    assert second_assessment["uncertainty"]["gradeSet"] == ["DEMO_GRADE_B"]
    snapshot = assessment_repository.get_supplemental_snapshot(
        second_assessment["supplementalAssessmentId"]
    )
    assert snapshot is not None
    assert snapshot.accepted_evidence == snapshot.accepted_evidence_set[-1]
    assert [item.quality_check_id for item in snapshot.accepted_evidence_set] == [
        first_quality["qualityCheckId"],
        second_quality["qualityCheckId"],
    ]
    assert [item.evidence_type for item in snapshot.accepted_evidence_set] == [
        "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
        "EXTERNAL_CONNECTED_SETTLEMENT_SUMMARY",
    ]
    assert [item.resolution_id for item in snapshot.accepted_evidence_set] == [
        None,
        second_selection["resolutionId"],
    ]
    assert all(
        item.boundary_check_id == second_selection["boundaryCheckId"]
        for item in snapshot.accepted_evidence_set
    )
    assert "sourceReference" not in second_assessment_response.text

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.SUPPLEMENTAL_ASSESSMENT_RUN
    assert event.output_summary["acceptedEvidenceCount"] == 2

    comparison_response = client.post(f"/v1/sessions/{session_id}/assessment/comparison")
    assert comparison_response.status_code == 200
    final_resolution_response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")
    assert final_resolution_response.status_code == 200
    assert final_resolution_response.json()["resolution"]["status"] == "RESOLVED"


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


def test_assessment_comparison_is_empty_before_creation(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/assessment/comparison")

    assert response.status_code == 200
    assert response.json() == {"sessionId": session_id, "comparison": None}


def test_assessment_comparison_requires_supplemental_assessment(
    client: TestClient,
) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/assessment/comparison")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUPPLEMENTAL_ASSESSMENT_NOT_READY"


def test_assessment_comparison_preserves_neutral_before_after_result(
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
    supplemental_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json=run_payload(submission["submissionId"]),
    )
    supplemental = supplemental_response.json()["supplementalAssessment"]

    first = client.post(f"/v1/sessions/{session_id}/assessment/comparison")
    second = client.post(f"/v1/sessions/{session_id}/assessment/comparison")
    latest = client.get(f"/v1/sessions/{session_id}/assessment/comparison")

    assert first.status_code == 200
    comparison = first.json()["comparison"]
    assert comparison["comparisonId"].startswith("acp_")
    assert comparison["baselineAssessmentId"] == baseline["assessmentId"]
    assert comparison["supplementalAssessmentId"] == supplemental["supplementalAssessmentId"]
    assert comparison["qualityCheckId"] == quality["qualityCheckId"]
    assert comparison["basis"] == "GRADE_SET"
    assert comparison["uncertaintyChange"] == "NARROWED"
    assert comparison["beforeUncertainty"]["gradeSet"] == [
        "DEMO_GRADE_B",
        "DEMO_GRADE_C",
    ]
    assert comparison["afterUncertainty"]["gradeSet"] == ["DEMO_GRADE_B"]
    assert comparison["rationaleCodes"] == ["GRADE_SET_PROPER_SUBSET"]
    assert comparison["baselineModelVersion"] == "demo-small-business-assessment-v1"
    assert (
        comparison["supplementalModelVersion"] == "demo-small-business-supplemental-assessment-v1"
    )
    assert comparison["comparedAt"].endswith("Z")
    assert comparison["demoOnly"] is True
    assert "improved" not in first.text.lower()
    assert "approved" not in first.text.lower()
    assert second.json() == first.json()
    assert latest.json() == first.json()
    assert assessment_repository.count_comparisons(session_id) == 1

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.ASSESSMENT_COMPARED
    assert event.request_id == first.headers["X-Request-ID"]
    assert event.input_version == supplemental["supplementalAssessmentId"]
    assert len(event.input_snapshot_hash) == 64
    assert event.data_version == supplemental["inputSnapshotId"]
    assert event.model_version == supplemental["modelVersion"]
    assert event.output_summary == {
        "comparisonBasis": "GRADE_SET",
        "uncertaintyChange": "NARROWED",
        "baselineAssessmentId": baseline["assessmentId"],
        "supplementalAssessmentId": supplemental["supplementalAssessmentId"],
        "demoOnly": True,
    }


def grade_uncertainty(
    *grades: str,
    mode: CalibrationMode = CalibrationMode.RULE_TABLE,
) -> AssessmentUncertainty:
    return AssessmentUncertainty(
        grade_set=list(grades),
        calibration_mode=mode,
        calibration_version="test-calibration-v1",
    )


@pytest.mark.parametrize(
    ("before", "after", "expected_basis", "expected_change"),
    [
        (
            grade_uncertainty("A", "B"),
            grade_uncertainty("A", "B"),
            "GRADE_SET",
            "UNCHANGED",
        ),
        (
            grade_uncertainty("A"),
            grade_uncertainty("A", "B"),
            "GRADE_SET",
            "EXPANDED",
        ),
        (
            grade_uncertainty("A", "B"),
            grade_uncertainty("B", "C"),
            "GRADE_SET",
            "SHIFTED",
        ),
        (
            grade_uncertainty("A"),
            grade_uncertainty("A", mode=CalibrationMode.CONFORMAL_CALIBRATED),
            "NOT_COMPARABLE",
            "NOT_COMPARABLE",
        ),
        (
            grade_uncertainty("A"),
            AssessmentUncertainty(
                grade_set=["A"],
                calibration_mode=CalibrationMode.RULE_TABLE,
                calibration_version="test-calibration-v2",
            ),
            "NOT_COMPARABLE",
            "NOT_COMPARABLE",
        ),
        (
            AssessmentUncertainty(
                lower_bound=0.1,
                upper_bound=0.9,
                calibration_mode=CalibrationMode.RULE_TABLE,
                calibration_version="test-calibration-v1",
            ),
            AssessmentUncertainty(
                lower_bound=0.2,
                upper_bound=0.7,
                calibration_mode=CalibrationMode.RULE_TABLE,
                calibration_version="test-calibration-v1",
            ),
            "NUMERIC_INTERVAL",
            "NARROWED",
        ),
    ],
)
def test_uncertainty_comparison_uses_structural_relationship_only(
    before: AssessmentUncertainty,
    after: AssessmentUncertainty,
    expected_basis: str,
    expected_change: str,
) -> None:
    basis, change, rationale_codes = compare_uncertainties(before, after)

    assert basis.value == expected_basis
    assert change.value == expected_change
    assert len(rationale_codes) == 1


def prepare_comparison(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    supplemental_catalog_path: Path = settings.demo_supplemental_assessments_path,
) -> tuple[str, dict, dict]:
    session_id = create_session(client)
    _, submission = prepare_submission(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    check_quality(client, session_id, submission["submissionId"])
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        supplemental_catalog_path
    )
    supplemental_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json=run_payload(submission["submissionId"]),
    )
    assert supplemental_response.status_code == 200
    comparison_response = client.post(f"/v1/sessions/{session_id}/assessment/comparison")
    assert comparison_response.status_code == 200
    return (
        session_id,
        supplemental_response.json()["supplementalAssessment"],
        comparison_response.json()["comparison"],
    )


def write_supplemental_catalog(
    path: Path,
    *,
    grades: list[str],
    calibration_version: str = "demo-uncertainty-rule-table-v1",
) -> None:
    path.write_text(
        json.dumps(
            {
                "dataVersion": "test-supplemental-assessments-v1",
                "assessments": [
                    {
                        "demoProfileId": "small-business",
                        "evidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
                        "result": {
                            "status": "COMPLETED",
                            "modelVersion": "test-supplemental-model-v1",
                            "uncertainty": {
                                "gradeSet": grades,
                                "calibrationMode": "RULE_TABLE",
                                "calibrationVersion": calibration_version,
                                "demoOnly": True,
                            },
                        },
                    }
                ],
                "demoOnly": True,
            }
        ),
        encoding="utf-8",
    )


def test_evidence_resolution_is_empty_before_creation(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/assessment/resolution")

    assert response.status_code == 200
    assert response.json() == {"sessionId": session_id, "resolution": None}


def test_evidence_resolution_requires_assessment_comparison(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSESSMENT_COMPARISON_NOT_READY"


def test_stable_supplemental_boundary_stops_evidence_collection(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id, supplemental, comparison = prepare_comparison(
        client,
        data_source_service,
        assessment_service,
        supplemental_assessment_service,
    )

    first = client.post(f"/v1/sessions/{session_id}/assessment/resolution")
    second = client.post(f"/v1/sessions/{session_id}/assessment/resolution")
    latest = client.get(f"/v1/sessions/{session_id}/assessment/resolution")

    assert first.status_code == 200
    resolution = first.json()["resolution"]
    assert resolution["resolutionId"].startswith("res_")
    assert resolution["comparisonId"] == comparison["comparisonId"]
    assert resolution["supplementalAssessmentId"] == supplemental["supplementalAssessmentId"]
    assert resolution["status"] == "RESOLVED"
    assert resolution["nextAction"] == "SHOW_UPDATED_RESULTS"
    assert resolution["stopEvidenceCollection"] is True
    assert resolution["underwriterRequired"] is False
    assert resolution["reasonCode"] == "PATH_STABLE"
    assert resolution["possibleRoutes"] == ["DEMO_PATH_1"]
    assert resolution["crossedBoundaryCodes"] == []
    assert resolution["calibrationVersion"] == "demo-uncertainty-rule-table-v1"
    assert resolution["boundaryPolicyVersion"] == "demo-policy-boundary-v1"
    assert resolution["resolvedAt"].endswith("Z")
    assert resolution["demoOnly"] is True
    assert second.json() == first.json()
    assert latest.json() == first.json()
    assert policy_boundary_repository.count_resolutions(session_id) == 1

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.EVIDENCE_COLLECTION_RESOLVED
    assert event.request_id == first.headers["X-Request-ID"]
    assert event.input_version == comparison["comparisonId"]
    assert len(event.input_snapshot_hash) == 64
    assert event.data_version == supplemental["inputSnapshotId"]
    assert event.model_version == supplemental["modelVersion"]
    assert event.policy_version == "demo-policy-boundary-v1"
    assert event.output_summary == {
        "resolutionStatus": "RESOLVED",
        "nextAction": "SHOW_UPDATED_RESULTS",
        "stopEvidenceCollection": True,
        "underwriterRequired": False,
        "reasonCode": "PATH_STABLE",
        "demoOnly": True,
    }


def test_ambiguous_supplemental_boundary_requests_more_evidence(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "ambiguous_supplemental.json"
    write_supplemental_catalog(
        catalog_path,
        grades=["DEMO_GRADE_B", "DEMO_GRADE_C"],
    )
    session_id, _, _ = prepare_comparison(
        client,
        data_source_service,
        assessment_service,
        supplemental_assessment_service,
        catalog_path,
    )

    response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")

    assert response.status_code == 200
    resolution = response.json()["resolution"]
    assert resolution["status"] == "MORE_EVIDENCE_REQUIRED"
    assert resolution["nextAction"] == "REQUEST_NEXT_EVIDENCE"
    assert resolution["stopEvidenceCollection"] is False
    assert resolution["underwriterRequired"] is False
    assert resolution["reasonCode"] == "POLICY_BOUNDARY_STILL_AMBIGUOUS"
    assert resolution["possibleRoutes"] == ["DEMO_PATH_1", "DEMO_PATH_2"]
    assert resolution["crossedBoundaryCodes"] == ["DEMO_BOUNDARY_1_2"]


def test_non_comparable_assessments_are_routed_to_underwriter(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "non_comparable_supplemental.json"
    write_supplemental_catalog(
        catalog_path,
        grades=["DEMO_GRADE_B"],
        calibration_version="different-calibration-v1",
    )
    session_id, _, comparison = prepare_comparison(
        client,
        data_source_service,
        assessment_service,
        supplemental_assessment_service,
        catalog_path,
    )
    assert comparison["uncertaintyChange"] == "NOT_COMPARABLE"

    response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")

    assert response.status_code == 200
    resolution = response.json()["resolution"]
    assert resolution["status"] == "HUMAN_REVIEW"
    assert resolution["nextAction"] == "UNDERWRITER_REVIEW"
    assert resolution["stopEvidenceCollection"] is True
    assert resolution["underwriterRequired"] is True
    assert resolution["reasonCode"] == "UNCERTAINTY_COMPARISON_NOT_RELIABLE"
    assert resolution["possibleRoutes"] == []
    assert resolution["crossedBoundaryCodes"] == []
