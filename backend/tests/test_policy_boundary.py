from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import DemoAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.policy_boundary_repository import SqlitePolicyBoundaryRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.assessment import AssessmentUncertainty, CalibrationMode
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService
from app.services.policy_boundary_service import DemoPolicyBoundaryCatalog


def create_session(client: TestClient) -> str:
    response = client.post("/v1/sessions/demo", json={"demoProfileId": "small-business"})
    assert response.status_code == 201
    return response.json()["sessionId"]


def prepare_completed_assessment(
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
    response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    assert response.status_code == 200
    assert response.json()["assessment"]["status"] == "COMPLETED"
    return response.json()["assessment"]


def test_boundary_check_is_empty_before_first_execution(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/assessment/boundary-check")

    assert response.status_code == 200
    assert response.json() == {"sessionId": session_id, "boundaryCheck": None}


def test_boundary_check_requires_completed_assessment(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSESSMENT_NOT_READY_FOR_BOUNDARY_CHECK"


def test_demo_grade_set_crosses_configured_policy_boundary(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    assessment = prepare_completed_assessment(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )

    response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")

    assert response.status_code == 200
    state = response.json()["boundaryCheck"]
    assert state["boundaryCheckId"].startswith("pbc_")
    assert state["assessmentId"] == assessment["assessmentId"]
    assert state["inputSnapshotId"] == assessment["inputSnapshotId"]
    assert state["calibrationVersion"] == "demo-uncertainty-rule-table-v1"
    assert state["policyVersion"] == "demo-policy-boundary-v1"
    assert state["demoOnly"] is True
    assert state["decision"] == {
        "status": "AMBIGUOUS",
        "possibleRoutes": ["DEMO_PATH_1", "DEMO_PATH_2"],
        "crossedBoundaryCodes": ["DEMO_BOUNDARY_1_2"],
        "stopReason": None,
        "underwriterRequired": False,
    }
    assert policy_boundary_repository.count_checks(session_id) == 1
    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.POLICY_BOUNDARY_CHECKED
    assert event.policy_version == "demo-policy-boundary-v1"
    assert event.model_version == "demo-small-business-assessment-v1"
    assert event.output_summary == {
        "boundaryStatus": "AMBIGUOUS",
        "possibleRouteCount": 2,
        "crossedBoundaryCount": 1,
        "underwriterRequired": False,
        "demoOnly": True,
    }

    reopened = SqlitePolicyBoundaryRepository(policy_boundary_repository.database_path)
    reopened.initialize()
    stored = reopened.get_latest(session_id)
    assert stored is not None
    assert stored.model_dump(mode="json", by_alias=True) == state


def test_same_versions_produce_same_boundary_decision(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    prepare_completed_assessment(client, session_id, data_source_service, assessment_service)

    first = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check").json()
    second = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check").json()
    latest = client.get(f"/v1/sessions/{session_id}/assessment/boundary-check").json()

    assert first["boundaryCheck"]["decision"] == second["boundaryCheck"]["decision"]
    assert first["boundaryCheck"]["policyVersion"] == second["boundaryCheck"]["policyVersion"]
    assert (
        first["boundaryCheck"]["calibrationVersion"]
        == second["boundaryCheck"]["calibrationVersion"]
    )
    assert latest == second


def test_catalog_stops_stable_and_unconfigured_paths() -> None:
    catalog = DemoPolicyBoundaryCatalog(settings.demo_policy_boundaries_path)
    stable = catalog.evaluate(
        AssessmentUncertainty(
            grade_set=["DEMO_GRADE_B"],
            calibration_mode=CalibrationMode.RULE_TABLE,
            calibration_version="test-rule-v1",
        )
    )
    blocked = catalog.evaluate(
        AssessmentUncertainty(
            grade_set=["UNKNOWN_DEMO_GRADE"],
            calibration_mode=CalibrationMode.RULE_TABLE,
            calibration_version="test-rule-v1",
        )
    )

    assert stable.status == "STABLE"
    assert stable.stop_reason == "PATH_STABLE"
    assert stable.underwriter_required is False
    assert blocked.status == "POLICY_BLOCKED"
    assert blocked.stop_reason == "DEMO_GRADE_POLICY_NOT_CONFIGURED"
    assert blocked.underwriter_required is True
