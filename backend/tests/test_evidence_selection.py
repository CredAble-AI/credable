import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    DemoAssessmentAdapter,
    DemoSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.evidence_selection_repository import SqliteEvidenceSelectionRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.schemas.policy_boundary import (
    BoundaryDecision,
    BoundaryStatus,
    PolicyBoundaryCheckResponse,
    PolicyBoundaryCheckState,
)
from app.services.assessment_service import AssessmentService, SupplementalAssessmentService
from app.services.data_source_service import DataSourceService
from app.services.evidence_quality_service import (
    DemoEvidenceQualityCatalog,
    EvidenceQualityService,
)
from app.services.evidence_selection_service import (
    DemoEvidenceCandidateCatalog,
    EvidenceSelectionService,
)
from app.services.policy_boundary_service import PolicyBoundaryService


def create_session(client: TestClient) -> str:
    response = client.post("/v1/sessions/demo", json={"demoProfileId": "small-business"})
    assert response.status_code == 201
    return response.json()["sessionId"]


def prepare_ambiguous_boundary(
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
    assessment_response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    assert assessment_response.json()["assessment"]["status"] == "COMPLETED"
    boundary_response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")
    assert boundary_response.status_code == 200
    assert boundary_response.json()["boundaryCheck"]["decision"]["status"] == "AMBIGUOUS"
    return boundary_response.json()["boundaryCheck"]


def write_supplemental_catalog(path: Path, grade_set: list[str]) -> None:
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
                                "pointEstimate": None,
                                "lowerBound": None,
                                "upperBound": None,
                                "gradeSet": grade_set,
                                "calibrationMode": "RULE_TABLE",
                                "calibrationVersion": "demo-uncertainty-rule-table-v1",
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


def prepare_resolution(
    client: TestClient,
    session_id: str,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    tmp_path: Path,
    *,
    grade_set: list[str],
) -> tuple[dict, dict]:
    boundary = prepare_ambiguous_boundary(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    selection_response = client.post(f"/v1/sessions/{session_id}/evidence/next")
    assert selection_response.status_code == 200
    selection = selection_response.json()["selection"]
    submission_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": selection["selectionId"],
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    )
    assert submission_response.status_code == 200
    submission = submission_response.json()["submission"]
    quality_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )
    assert quality_response.status_code == 200

    catalog_path = tmp_path / "supplemental.json"
    write_supplemental_catalog(catalog_path, grade_set)
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(catalog_path)
    supplemental_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json={"submissionId": submission["submissionId"]},
    )
    assert supplemental_response.status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/comparison").status_code == 200
    resolution_response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")
    assert resolution_response.status_code == 200
    return boundary, resolution_response.json()["resolution"]


def test_evidence_selection_is_empty_before_first_selection(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    assert response.json() == {"sessionId": session_id, "selection": None}


def test_evidence_selection_requires_policy_boundary_check(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "POLICY_BOUNDARY_CHECK_NOT_READY"


def test_ambiguous_boundary_selects_one_minimum_evidence(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_selection_repository: SqliteEvidenceSelectionRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    boundary = prepare_ambiguous_boundary(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    state = response.json()["selection"]
    assert state["selectionId"].startswith("evs_")
    assert state["boundaryCheckId"] == boundary["boundaryCheckId"]
    assert state["resolutionId"] is None
    assert state["rejectedQualityCheckId"] is None
    assert state["iteration"] == 1
    assert state["maxEvidenceRequests"] == 2
    assert state["status"] == "SELECTED"
    assert state["evaluatedCandidateCount"] == 2
    assert state["stopReason"] is None
    assert state["underwriterRequired"] is False
    assert state["calibrationVersion"] == "demo-uncertainty-rule-table-v1"
    assert state["boundaryPolicyVersion"] == "demo-policy-boundary-v1"
    assert state["selectionPolicyVersion"] == "demo-novel-evidence-selection-v4"
    assert state["sourceCreditAssessmentId"] == "bca_demo_001"
    assert state["informationGapCodes"] == [
        "DEMO_INFORMATION_GAP",
        "DEMO_RECENT_PERFORMANCE_NOT_REFLECTED",
    ]
    assert state["baselineFeatureSnapshotId"].startswith("fts_")
    assert state["baselineInformationCoverageCodes"] == ["BANK_CASH_FLOW_TOTALS"]
    assert state["demoOnly"] is True
    assert state["selectedEvidence"] == {
        "evidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
        "displayName": "최근 매출·입금 요약",
        "description": "최근 매출 발생과 실제 입금 흐름을 확인할 수 있는 고객 제출 자료",
        "sourceType": "CUSTOMER_SUBMITTED",
        "collectionMode": "DEMO_FILE_UPLOAD",
        "availability": "CONSENT_REQUIRED",
        "rationaleCodes": [
            "DEMO_RESOLVE_BOUNDARY_1_2",
            "DEMO_MINIMUM_SINGLE_REQUEST",
        ],
        "matchedInformationGapCodes": [
            "DEMO_INFORMATION_GAP",
            "DEMO_RECENT_PERFORMANCE_NOT_REFLECTED",
        ],
        "informationContentCodes": [
            "BANK_CASH_FLOW_TOTALS",
            "DEPOSIT_TO_REVENUE_RECONCILIATION",
            "RECENT_REVENUE_SERIES",
        ],
        "novelInformationCodes": [
            "DEPOSIT_TO_REVENUE_RECONCILIATION",
            "RECENT_REVENUE_SERIES",
        ],
        "overlappingInformationCodes": ["BANK_CASH_FLOW_TOTALS"],
        "consentScope": {
            "scopeVersion": "demo-recent-revenue-consent-v1",
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
        },
        "demoOnly": True,
    }
    assert evidence_selection_repository.count_selections(session_id) == 1
    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.EVIDENCE_SELECTED
    assert event.policy_version == "demo-novel-evidence-selection-v4"
    assert event.output_summary == {
        "selectionStatus": "SELECTED",
        "iteration": 1,
        "maxEvidenceRequests": 2,
        "evaluatedCandidateCount": 2,
        "underwriterRequired": False,
        "calibrationVersion": "demo-uncertainty-rule-table-v1",
        "informationGapCount": 2,
        "baselineInformationCoverageCount": 1,
        "demoOnly": True,
        "sourceCreditAssessmentId": "bca_demo_001",
        "selectedEvidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
        "evidenceValue": 0.5,
        "matchedInformationGapCount": 2,
        "novelInformationCount": 2,
        "overlappingInformationCount": 1,
    }

    reopened = SqliteEvidenceSelectionRepository(evidence_selection_repository.database_path)
    reopened.initialize()
    stored = reopened.get_latest(session_id)
    assert stored is not None
    assert stored.model_dump(mode="json", by_alias=True) == state


def test_same_boundary_check_does_not_create_duplicate_request(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_selection_repository: SqliteEvidenceSelectionRepository,
) -> None:
    session_id = create_session(client)
    prepare_ambiguous_boundary(client, session_id, data_source_service, assessment_service)

    first = client.post(f"/v1/sessions/{session_id}/evidence/next").json()
    second = client.post(f"/v1/sessions/{session_id}/evidence/next").json()
    latest = client.get(f"/v1/sessions/{session_id}/evidence/next").json()

    assert second == first
    assert latest == first
    assert evidence_selection_repository.count_selections(session_id) == 1


def test_rejected_quality_selects_next_unsubmitted_candidate(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_quality_service: EvidenceQualityService,
    evidence_selection_repository: SqliteEvidenceSelectionRepository,
    session_repository: SqliteCustomerSessionRepository,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    boundary = prepare_ambiguous_boundary(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    first_selection = client.post(f"/v1/sessions/{session_id}/evidence/next").json()["selection"]
    submission_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": first_selection["selectionId"],
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    )
    assert submission_response.status_code == 200
    submission = submission_response.json()["submission"]
    quality_catalog = json.loads(settings.demo_evidence_quality_path.read_text(encoding="utf-8"))
    freshness = next(
        item for item in quality_catalog["results"][0]["checks"] if item["dimension"] == "FRESHNESS"
    )
    freshness.update(
        status="NOT_VERIFIED",
        rationaleCode="DEMO_FRESHNESS_NOT_VERIFIED",
    )
    catalog_path = tmp_path / "rejected-quality.json"
    catalog_path.write_text(json.dumps(quality_catalog), encoding="utf-8")
    evidence_quality_service.catalog = DemoEvidenceQualityCatalog(catalog_path)
    quality_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )
    assert quality_response.status_code == 200
    quality = quality_response.json()["quality"]
    assert quality["status"] == "REJECTED"

    first = client.post(f"/v1/sessions/{session_id}/evidence/next")
    repeated = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert first.status_code == 200
    assert repeated.json() == first.json()
    selection = first.json()["selection"]
    assert selection["boundaryCheckId"] == boundary["boundaryCheckId"]
    assert selection["resolutionId"] is None
    assert selection["rejectedQualityCheckId"] == quality["qualityCheckId"]
    assert selection["iteration"] == 2
    assert selection["status"] == "SELECTED"
    assert selection["selectedEvidence"]["evidenceType"] == (
        "EXTERNAL_CONNECTED_SETTLEMENT_SUMMARY"
    )
    assert evidence_selection_repository.count_selections(session_id) == 2
    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.EVIDENCE_SELECTED
    assert event.input_version == quality["qualityCheckId"]
    assert event.data_version == quality["dataVersion"]
    assert event.output_summary["rejectedQualityCheckId"] == quality["qualityCheckId"]
    assert event.output_summary["iteration"] == 2


def test_rejected_quality_routes_to_review_when_no_candidate_remains(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_quality_service: EvidenceQualityService,
    evidence_selection_service: EvidenceSelectionService,
    tmp_path: Path,
) -> None:
    single_candidate = json.loads(
        settings.demo_evidence_candidates_path.read_text(encoding="utf-8")
    )
    single_candidate["candidates"] = single_candidate["candidates"][:1]
    candidate_path = tmp_path / "single-candidate-recovery.json"
    candidate_path.write_text(json.dumps(single_candidate), encoding="utf-8")
    evidence_selection_service.catalog = DemoEvidenceCandidateCatalog(candidate_path)
    session_id = create_session(client)
    prepare_ambiguous_boundary(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    selection = client.post(f"/v1/sessions/{session_id}/evidence/next").json()["selection"]
    submission = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": selection["selectionId"],
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    ).json()["submission"]
    quality_catalog = json.loads(settings.demo_evidence_quality_path.read_text(encoding="utf-8"))
    quality_catalog["results"][0]["checks"][1].update(
        status="NOT_VERIFIED",
        rationaleCode="DEMO_FRESHNESS_NOT_VERIFIED",
    )
    quality_path = tmp_path / "rejected-single-quality.json"
    quality_path.write_text(json.dumps(quality_catalog), encoding="utf-8")
    evidence_quality_service.catalog = DemoEvidenceQualityCatalog(quality_path)
    quality = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    ).json()["quality"]
    assert quality["status"] == "REJECTED"

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    recovered = response.json()["selection"]
    assert recovered["rejectedQualityCheckId"] == quality["qualityCheckId"]
    assert recovered["status"] == "HUMAN_REVIEW"
    assert recovered["stopReason"] == "NO_NEW_USEFUL_EVIDENCE"
    assert recovered["underwriterRequired"] is True


def test_ambiguous_boundary_without_source_assessment_lineage_requires_review(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_selection_service: EvidenceSelectionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = create_session(client)
    boundary = prepare_ambiguous_boundary(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    baseline = assessment_service.repository.get_for_session(
        session_id,
        boundary["assessmentId"],
    )
    assert baseline is not None
    monkeypatch.setattr(
        evidence_selection_service.assessment_repository,
        "get_for_session",
        lambda *_: baseline.model_copy(update={"source_assessment": None}),
    )

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["status"] == "HUMAN_REVIEW"
    assert selection["stopReason"] == "SOURCE_ASSESSMENT_LINEAGE_NOT_READY"
    assert selection["selectedEvidence"] is None
    assert selection["underwriterRequired"] is True


def test_unmapped_source_information_gap_is_not_guessed(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_selection_service: EvidenceSelectionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = create_session(client)
    boundary = prepare_ambiguous_boundary(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    baseline = assessment_service.repository.get_for_session(
        session_id,
        boundary["assessmentId"],
    )
    assert baseline is not None
    assert baseline.source_assessment is not None
    unmapped_source = baseline.source_assessment.model_copy(
        update={"reason_codes": ["DEMO_UNMAPPED_INFORMATION_GAP"]}
    )
    monkeypatch.setattr(
        evidence_selection_service.assessment_repository,
        "get_for_session",
        lambda *_: baseline.model_copy(update={"source_assessment": unmapped_source}),
    )

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["status"] == "HUMAN_REVIEW"
    assert selection["stopReason"] == "NO_CANDIDATE_FOR_INFORMATION_GAP"
    assert selection["informationGapCodes"] == ["DEMO_UNMAPPED_INFORMATION_GAP"]
    assert selection["selectedEvidence"] is None
    assert selection["underwriterRequired"] is True


def test_missing_baseline_information_coverage_requires_review(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_selection_service: EvidenceSelectionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = create_session(client)
    prepare_ambiguous_boundary(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    monkeypatch.setattr(
        evidence_selection_service.feature_snapshot_repository,
        "get",
        lambda *_: None,
    )

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["status"] == "HUMAN_REVIEW"
    assert selection["stopReason"] == "BASELINE_INFORMATION_COVERAGE_NOT_READY"
    assert selection["selectedEvidence"] is None
    assert selection["underwriterRequired"] is True


def test_fully_overlapping_evidence_is_not_requested(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_selection_service: EvidenceSelectionService,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    prepare_ambiguous_boundary(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    catalog_data = json.loads(settings.demo_evidence_candidates_path.read_text(encoding="utf-8"))
    catalog_data["candidates"] = [catalog_data["candidates"][0]]
    catalog_data["candidates"][0]["informationContentCodes"] = ["BANK_CASH_FLOW_TOTALS"]
    catalog_path = tmp_path / "fully-overlapping-candidates.json"
    catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")
    evidence_selection_service.catalog = DemoEvidenceCandidateCatalog(catalog_path)

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["status"] == "HUMAN_REVIEW"
    assert selection["stopReason"] == "NO_NOVEL_EVIDENCE"
    assert selection["evaluatedCandidateCount"] == 1
    assert selection["baselineInformationCoverageCodes"] == ["BANK_CASH_FLOW_TOTALS"]
    assert selection["selectedEvidence"] is None
    assert selection["underwriterRequired"] is True


@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_reason", "underwriter_required"),
    [
        (
            BoundaryDecision(
                status=BoundaryStatus.STABLE,
                possible_routes=["DEMO_PATH_1"],
                crossed_boundary_codes=[],
                stop_reason="PATH_STABLE",
                underwriter_required=False,
            ),
            "NOT_REQUIRED",
            "PATH_STABLE",
            False,
        ),
        (
            BoundaryDecision(
                status=BoundaryStatus.POLICY_BLOCKED,
                possible_routes=[],
                crossed_boundary_codes=[],
                stop_reason="DEMO_POLICY_NOT_CONFIGURED",
                underwriter_required=True,
            ),
            "POLICY_BLOCKED",
            "DEMO_POLICY_NOT_CONFIGURED",
            True,
        ),
    ],
)
def test_stopped_boundary_does_not_select_evidence(
    client: TestClient,
    policy_boundary_service: PolicyBoundaryService,
    monkeypatch: pytest.MonkeyPatch,
    decision: BoundaryDecision,
    expected_status: str,
    expected_reason: str,
    underwriter_required: bool,
) -> None:
    session_id = create_session(client)
    boundary_check = PolicyBoundaryCheckState(
        boundary_check_id=f"pbc_{expected_status.lower()}",
        assessment_id="asm_test",
        checked_at=datetime.now(UTC),
        decision=decision,
        input_snapshot_id="dss_test",
        calibration_version="test-rule-v1",
        policy_version="demo-policy-boundary-v1",
    )
    monkeypatch.setattr(
        policy_boundary_service,
        "get_latest",
        lambda requested_session_id: PolicyBoundaryCheckResponse(
            session_id=requested_session_id,
            boundary_check=boundary_check,
        ),
    )

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["status"] == expected_status
    assert selection["selectedEvidence"] is None
    assert selection["evaluatedCandidateCount"] == 0
    assert selection["stopReason"] == expected_reason
    assert selection["underwriterRequired"] is underwriter_required


def test_more_evidence_resolution_selects_next_unsubmitted_candidate(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    evidence_selection_repository: SqliteEvidenceSelectionRepository,
    session_repository: SqliteCustomerSessionRepository,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    boundary, resolution = prepare_resolution(
        client,
        session_id,
        data_source_service,
        assessment_service,
        supplemental_assessment_service,
        tmp_path,
        grade_set=["DEMO_GRADE_B", "DEMO_GRADE_C"],
    )
    assert resolution["status"] == "MORE_EVIDENCE_REQUIRED"

    first = client.post(f"/v1/sessions/{session_id}/evidence/next")
    second = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert first.status_code == 200
    assert second.json() == first.json()
    selection = first.json()["selection"]
    assert selection["boundaryCheckId"] == boundary["boundaryCheckId"]
    assert selection["resolutionId"] == resolution["resolutionId"]
    assert selection["iteration"] == 2
    assert selection["status"] == "SELECTED"
    assert selection["selectedEvidence"]["evidenceType"] == (
        "EXTERNAL_CONNECTED_SETTLEMENT_SUMMARY"
    )
    assert selection["selectedEvidence"]["consentScope"]["scopeVersion"] == (
        "demo-settlement-connection-consent-v1"
    )
    assert selection["evaluatedCandidateCount"] == 1
    assert evidence_selection_repository.count_selections(session_id) == 2

    consent = client.get(
        f"/v1/sessions/{session_id}/evidence/selections/{selection['selectionId']}/consent"
    )
    assert consent.status_code == 200
    assert consent.json()["consent"]["sourceType"] == "EXTERNAL_CONNECTED"
    assert consent.json()["consent"]["status"] == "PENDING"
    option = client.get(
        f"/v1/sessions/{session_id}/evidence/selections/"
        f"{selection['selectionId']}/submission-option"
    )
    assert option.status_code == 200
    assert option.json()["collectionMode"] == "DEMO_CONNECTION"
    assert option.json()["submissionRequirement"]["status"] == "CONSENT_REQUIRED"
    assert option.json()["demoFile"] is None
    assert option.json()["uploadPolicy"] is None

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.EVIDENCE_SELECTED
    assert event.input_version == resolution["resolutionId"]
    assert event.data_version == resolution["supplementalAssessmentId"]
    assert event.output_summary["resolutionId"] == resolution["resolutionId"]
    assert event.output_summary["iteration"] == 2
    assert event.output_summary["selectedEvidenceType"] == ("EXTERNAL_CONNECTED_SETTLEMENT_SUMMARY")


def test_rejected_quality_after_resolution_uses_latest_lineage(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    _, resolution = prepare_resolution(
        client,
        session_id,
        data_source_service,
        assessment_service,
        supplemental_assessment_service,
        tmp_path,
        grade_set=["DEMO_GRADE_B", "DEMO_GRADE_C"],
    )
    second_selection = client.post(f"/v1/sessions/{session_id}/evidence/next").json()["selection"]
    assert second_selection["resolutionId"] == resolution["resolutionId"]
    submission = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": second_selection["selectionId"],
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    ).json()["submission"]
    quality_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )
    assert quality_response.status_code == 200
    quality = quality_response.json()["quality"]
    assert quality["status"] == "REJECTED"

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["resolutionId"] is None
    assert selection["rejectedQualityCheckId"] == quality["qualityCheckId"]
    assert selection["iteration"] == 3
    assert selection["status"] == "HUMAN_REVIEW"
    assert selection["stopReason"] == "NO_NEW_USEFUL_EVIDENCE"


def test_closed_resolution_blocks_another_evidence_selection(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    _, resolution = prepare_resolution(
        client,
        session_id,
        data_source_service,
        assessment_service,
        supplemental_assessment_service,
        tmp_path,
        grade_set=["DEMO_GRADE_B"],
    )
    assert resolution["status"] == "RESOLVED"

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_COLLECTION_CLOSED"


def test_repeat_selection_stops_when_no_new_candidate_remains(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    evidence_selection_service: EvidenceSelectionService,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    _, resolution = prepare_resolution(
        client,
        session_id,
        data_source_service,
        assessment_service,
        supplemental_assessment_service,
        tmp_path,
        grade_set=["DEMO_GRADE_B", "DEMO_GRADE_C"],
    )
    single_candidate_path = tmp_path / "single-candidate.json"
    catalog = json.loads(settings.demo_evidence_candidates_path.read_text(encoding="utf-8"))
    catalog["candidates"] = catalog["candidates"][:1]
    single_candidate_path.write_text(json.dumps(catalog), encoding="utf-8")
    evidence_selection_service.catalog = DemoEvidenceCandidateCatalog(single_candidate_path)

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["resolutionId"] == resolution["resolutionId"]
    assert selection["iteration"] == 2
    assert selection["status"] == "HUMAN_REVIEW"
    assert selection["selectedEvidence"] is None
    assert selection["evaluatedCandidateCount"] == 0
    assert selection["stopReason"] == "NO_NEW_USEFUL_EVIDENCE"
    assert selection["underwriterRequired"] is True


def test_repository_migrates_legacy_selection_table_without_data_loss(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.db"
    legacy_state = {
        "selectionId": "evs_legacy",
        "boundaryCheckId": "pbc_legacy",
        "iteration": 1,
        "status": "NOT_REQUIRED",
        "selectedEvidence": None,
        "evaluatedCandidateCount": 0,
        "stopReason": "PATH_STABLE",
        "underwriterRequired": False,
        "selectedAt": "2026-09-05T00:00:00Z",
        "calibrationVersion": "test-calibration-v1",
        "boundaryPolicyVersion": "test-boundary-v1",
        "selectionPolicyVersion": "test-selection-v1",
        "demoOnly": True,
    }
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE customer_sessions (
                session_id TEXT PRIMARY KEY
            );
            INSERT INTO customer_sessions(session_id) VALUES ('ses_legacy');

            CREATE TABLE evidence_selections (
                selection_order INTEGER PRIMARY KEY AUTOINCREMENT,
                selection_id TEXT NOT NULL UNIQUE,
                boundary_check_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                selected_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
            );
            """
        )
        connection.execute(
            """
            INSERT INTO evidence_selections(
                selection_id,
                boundary_check_id,
                session_id,
                state_json,
                selected_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "evs_legacy",
                "pbc_legacy",
                "ses_legacy",
                json.dumps(legacy_state),
                "2026-09-05T00:00:00+00:00",
            ),
        )

    repository = SqliteEvidenceSelectionRepository(database_path)
    repository.initialize()

    stored = repository.get_latest("ses_legacy")
    assert stored is not None
    assert stored.selection_id == "evs_legacy"
    assert stored.resolution_id is None
    assert stored.rejected_quality_check_id is None
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(evidence_selections)").fetchall()
        }
    assert "resolution_id" in columns
    assert "rejected_quality_check_id" in columns


def test_request_limit_stops_selection_while_useful_candidates_remain(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    evidence_selection_service: EvidenceSelectionService,
    tmp_path: Path,
) -> None:
    catalog_data = json.loads(settings.demo_evidence_candidates_path.read_text(encoding="utf-8"))
    spare = json.loads(json.dumps(catalog_data["candidates"][1]))
    spare["evidenceType"] = "EXTERNAL_CONNECTED_SPARE_SUMMARY"
    spare["informationContentCodes"] = ["SPARE_SERIES", "SPARE_RECONCILIATION"]
    spare["consentScope"]["scopeVersion"] = "demo-spare-consent-v1"
    catalog_data["candidates"].append(spare)
    catalog_path = tmp_path / "three-candidates.json"
    catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")
    evidence_selection_service.catalog = DemoEvidenceCandidateCatalog(catalog_path)
    assert evidence_selection_service.catalog.max_evidence_requests == 2

    session_id = create_session(client)
    _, resolution = prepare_resolution(
        client,
        session_id,
        data_source_service,
        assessment_service,
        supplemental_assessment_service,
        tmp_path,
        grade_set=["DEMO_GRADE_B", "DEMO_GRADE_C"],
    )
    second_selection = client.post(f"/v1/sessions/{session_id}/evidence/next").json()["selection"]
    assert second_selection["iteration"] == 2
    assert second_selection["status"] == "SELECTED"
    submission = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": second_selection["selectionId"],
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    ).json()["submission"]
    quality = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    ).json()["quality"]
    assert quality["status"] == "REJECTED"

    response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["iteration"] == 3
    assert selection["maxEvidenceRequests"] == 2
    assert selection["status"] == "HUMAN_REVIEW"
    assert selection["stopReason"] == "EVIDENCE_REQUEST_LIMIT_REACHED"
    assert selection["underwriterRequired"] is True
    assert selection["selectedEvidence"] is None
    assert selection["evaluatedCandidateCount"] == 1
