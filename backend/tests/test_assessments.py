import pytest
from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import AssessmentAdapter, DemoAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.assessment_repository import SqliteAssessmentRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.assessment import (
    AdapterAssessmentResult,
    AssessmentInputSnapshot,
    AssessmentSnapshotType,
    AssessmentUncertainty,
    CalibrationMode,
)
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService


def create_session(client: TestClient, demo_profile_id: str = "startup") -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def prepare_required_demo_sources(
    client: TestClient,
    session_id: str,
    data_source_service: DataSourceService,
) -> None:
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    for source_type in (
        ConsentSourceType.BANK_INTERNAL,
        ConsentSourceType.CREDIT_INFORMATION,
    ):
        response = client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant")
        assert response.status_code == 200
    response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")
    assert response.status_code == 200


class FailingAssessmentAdapter(AssessmentAdapter):
    def run(self, snapshot: AssessmentInputSnapshot) -> AdapterAssessmentResult:
        del snapshot
        raise RuntimeError("private model detail must not escape")

    def is_ready(self) -> bool:
        return True


def test_assessment_is_not_run_before_first_execution(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/assessment")

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": session_id,
        "assessment": {
            "assessmentId": None,
            "status": "NOT_RUN",
            "calculatedAt": None,
            "inputSnapshotId": None,
            "modelVersion": None,
            "reasonCode": None,
            "uncertainty": None,
            "demoOnly": True,
        },
    }


def test_run_without_model_returns_explicit_state_and_preserves_snapshot(
    client: TestClient,
    assessment_repository: SqliteAssessmentRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/assessment/run")

    assert response.status_code == 200
    body = response.json()
    assessment = body["assessment"]
    assert body["sessionId"] == session_id
    assert set(assessment) == {
        "assessmentId",
        "status",
        "calculatedAt",
        "inputSnapshotId",
        "modelVersion",
        "reasonCode",
        "uncertainty",
        "demoOnly",
    }
    assert assessment["assessmentId"].startswith("asm_")
    assert assessment["status"] == "MODEL_NOT_CONFIGURED"
    assert assessment["calculatedAt"].endswith("Z")
    assert assessment["inputSnapshotId"].startswith("dss_")
    assert assessment["modelVersion"] is None
    assert assessment["reasonCode"] == "DEMO_ASSESSMENT_MODEL_NOT_CONFIGURED"
    assert assessment["uncertainty"] is None
    assert assessment["demoOnly"] is True
    assert "score" not in response.text.lower()
    assert "grade" not in response.text.lower()

    reopened = SqliteAssessmentRepository(assessment_repository.database_path)
    reopened.initialize()
    stored = reopened.get_latest(session_id)
    assert stored is not None
    assert stored.model_dump(mode="json", by_alias=True) == assessment

    snapshot = reopened.get_snapshot(assessment["assessmentId"])
    assert snapshot is not None
    assert snapshot.session_id == session_id
    assert snapshot.demo_profile_id == "startup"
    assert len(snapshot.data_sources) == 4
    assert {item.retrieval_status for item in snapshot.data_sources} == {"CONSENT_REQUIRED"}
    assert snapshot.source_snapshots == []
    assert snapshot.feature_snapshot is None

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.ASSESSMENT_RUN
    assert event.request_id == response.headers["X-Request-ID"]
    assert event.input_snapshot_hash == assessment["inputSnapshotId"].removeprefix("dss_")
    assert event.model_version is None
    assert event.output_summary == {
        "assessmentStatus": "MODEL_NOT_CONFIGURED",
        "demoOnly": True,
    }


def test_demo_assessment_requires_verified_bank_sources(
    client: TestClient,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client, "small-business")
    adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    assessment_service.adapter = adapter

    response = client.post(f"/v1/sessions/{session_id}/assessment/run")

    assert adapter.is_ready() is True
    assert response.status_code == 200
    assessment = response.json()["assessment"]
    assert assessment["status"] == "INSUFFICIENT_DATA"
    assert assessment["reasonCode"] == "DEMO_REQUIRED_DATA_NOT_VERIFIED"
    assert assessment["modelVersion"] is None


def test_demo_assessment_completes_small_business_fixture(
    client: TestClient,
    assessment_service: AssessmentService,
    data_source_service: DataSourceService,
    session_repository: SqliteCustomerSessionRepository,
    assessment_repository: SqliteAssessmentRepository,
) -> None:
    session_id = create_session(client, "small-business")
    prepare_required_demo_sources(client, session_id, data_source_service)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)

    response = client.post(f"/v1/sessions/{session_id}/assessment/run")

    assert response.status_code == 200
    assessment = response.json()["assessment"]
    assert assessment["status"] == "COMPLETED"
    assert assessment["modelVersion"] == "demo-small-business-assessment-v1"
    assert assessment["reasonCode"] is None
    assert assessment["uncertainty"] == {
        "pointEstimate": None,
        "lowerBound": None,
        "upperBound": None,
        "gradeSet": ["DEMO_GRADE_B", "DEMO_GRADE_C"],
        "calibrationMode": "RULE_TABLE",
        "calibrationVersion": "demo-uncertainty-rule-table-v1",
        "demoOnly": True,
    }
    assert assessment["demoOnly"] is True
    snapshot = assessment_repository.get_snapshot(assessment["assessmentId"])
    assert snapshot is not None
    assert {item.snapshot_type for item in snapshot.source_snapshots} == {
        AssessmentSnapshotType.BANK_ACCOUNT_DATA,
        AssessmentSnapshotType.BANK_CREDIT_HISTORY,
        AssessmentSnapshotType.BANK_LOAN_HISTORY,
        AssessmentSnapshotType.EXTERNAL_CREDIT_EXPOSURE,
    }
    assert {item.source_type for item in snapshot.source_snapshots} == {
        ConsentSourceType.BANK_INTERNAL,
        ConsentSourceType.CREDIT_INFORMATION,
    }
    assert all(len(item.snapshot_hash) == 64 for item in snapshot.source_snapshots)
    assert snapshot.feature_snapshot is not None
    assert snapshot.feature_snapshot.feature_snapshot_id.startswith("fts_")
    assert snapshot.feature_snapshot.feature_set_version == "demo-neutral-feature-set-v1"
    assert len(snapshot.feature_snapshot.snapshot_hash) == 64
    event = session_repository.list_audit_events(session_id)[-1]
    assert event.output_summary == {
        "assessmentStatus": "COMPLETED",
        "calibrationMode": "RULE_TABLE",
        "calibrationVersion": "demo-uncertainty-rule-table-v1",
        "demoOnly": True,
    }


def test_demo_assessment_keeps_startup_as_insufficient_data(
    client: TestClient,
    assessment_service: AssessmentService,
    data_source_service: DataSourceService,
    assessment_repository: SqliteAssessmentRepository,
) -> None:
    session_id = create_session(client)
    prepare_required_demo_sources(client, session_id, data_source_service)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)

    response = client.post(f"/v1/sessions/{session_id}/assessment/run")

    assessment = response.json()["assessment"]
    assert assessment["status"] == "INSUFFICIENT_DATA"
    assert assessment["reasonCode"] == "DEMO_VERIFIED_DATA_INSUFFICIENT"
    assert assessment["modelVersion"] is None
    assert assessment["uncertainty"] is None
    assert "score" not in response.text.lower()
    assert "grade" not in response.text.lower()
    snapshot = assessment_repository.get_snapshot(assessment["assessmentId"])
    assert snapshot is not None
    assert len(snapshot.source_snapshots) == 4
    assert snapshot.feature_snapshot is not None


def test_each_run_is_preserved_and_get_returns_latest(
    client: TestClient,
    assessment_repository: SqliteAssessmentRepository,
) -> None:
    session_id = create_session(client)

    first = client.post(f"/v1/sessions/{session_id}/assessment/run").json()
    second = client.post(f"/v1/sessions/{session_id}/assessment/run").json()
    latest = client.get(f"/v1/sessions/{session_id}/assessment").json()

    assert first["assessment"]["assessmentId"] != second["assessment"]["assessmentId"]
    assert assessment_repository.count_executions(session_id) == 2
    assert latest == second


def test_input_snapshot_changes_when_data_source_state_changes(
    client: TestClient,
) -> None:
    session_id = create_session(client)
    first = client.post(f"/v1/sessions/{session_id}/assessment/run").json()

    client.post(f"/v1/sessions/{session_id}/consents/BANK_INTERNAL/grant")
    client.post(f"/v1/sessions/{session_id}/data-sources/refresh")
    second = client.post(f"/v1/sessions/{session_id}/assessment/run").json()

    assert first["assessment"]["inputSnapshotId"] != second["assessment"]["inputSnapshotId"]


def test_adapter_failure_is_sanitized_and_persisted(
    client: TestClient,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    assessment_service.adapter = FailingAssessmentAdapter()

    response = client.post(f"/v1/sessions/{session_id}/assessment/run")

    assert response.status_code == 200
    assert response.json()["assessment"]["status"] == "FAILED"
    assert response.json()["assessment"]["reasonCode"] == "ASSESSMENT_ADAPTER_ERROR"
    assert "private model detail" not in response.text


def test_unknown_session_uses_standard_error(client: TestClient) -> None:
    response = client.post("/v1/sessions/ses_missing/assessment/run")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_SESSION_NOT_FOUND"
    assert response.json()["error"]["requestId"].startswith("req_")


def test_uncertainty_requires_a_complete_interval_or_grade_set() -> None:
    with pytest.raises(ValueError, match="both bounds"):
        AssessmentUncertainty(
            lower_bound=0.1,
            calibration_mode=CalibrationMode.RULE_TABLE,
            calibration_version="test-rule-v1",
        )

    with pytest.raises(ValueError, match="interval or gradeSet"):
        AssessmentUncertainty(
            calibration_mode=CalibrationMode.RULE_TABLE,
            calibration_version="test-rule-v1",
        )


def test_uncertainty_rejects_inconsistent_values() -> None:
    with pytest.raises(ValueError, match="within the uncertainty interval"):
        AssessmentUncertainty(
            point_estimate=0.8,
            lower_bound=0.2,
            upper_bound=0.6,
            calibration_mode=CalibrationMode.CONFORMAL_CALIBRATED,
            calibration_version="test-calibration-v1",
        )

    with pytest.raises(ValueError, match="must be unique"):
        AssessmentUncertainty(
            grade_set=["DEMO_GRADE_B", "DEMO_GRADE_B"],
            calibration_mode=CalibrationMode.RULE_TABLE,
            calibration_version="test-rule-v1",
        )
