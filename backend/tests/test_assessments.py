from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import AssessmentAdapter
from app.repositories.assessment_repository import SqliteAssessmentRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.assessment import AdapterAssessmentResult, AssessmentInputSnapshot
from app.schemas.audit import AuditStage
from app.services.assessment_service import AssessmentService


def create_session(client: TestClient) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "startup"},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


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
        "demoOnly",
    }
    assert assessment["assessmentId"].startswith("asm_")
    assert assessment["status"] == "MODEL_NOT_CONFIGURED"
    assert assessment["calculatedAt"].endswith("Z")
    assert assessment["inputSnapshotId"].startswith("dss_")
    assert assessment["modelVersion"] is None
    assert assessment["reasonCode"] == "DEMO_ASSESSMENT_MODEL_NOT_CONFIGURED"
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

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.ASSESSMENT_RUN
    assert event.request_id == response.headers["X-Request-ID"]
    assert event.input_snapshot_hash == assessment["inputSnapshotId"].removeprefix("dss_")
    assert event.model_version is None
    assert event.output_summary == {
        "assessmentStatus": "MODEL_NOT_CONFIGURED",
        "demoOnly": True,
    }


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
