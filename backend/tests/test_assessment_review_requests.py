from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    DemoAssessmentAdapter,
    DemoSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditActor, AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService, SupplementalAssessmentService
from app.services.data_source_service import DataSourceService

ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-api-key"}


def create_session(client: TestClient) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"businessBorrowerType": "SOLE_PROPRIETOR"},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def run_baseline(
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
    assessment = response.json()["assessment"]
    assert assessment["status"] == "COMPLETED"
    return assessment


def run_supplemental(
    client: TestClient,
    session_id: str,
    supplemental_assessment_service: SupplementalAssessmentService,
) -> dict:
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
    submission_id = submission_response.json()["submission"]["submissionId"]
    quality_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission_id}/quality"
    )
    assert quality_response.status_code == 200
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        settings.demo_supplemental_assessments_path
    )
    response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json={"submissionId": submission_id},
    )
    assert response.status_code == 200
    supplemental = response.json()["supplementalAssessment"]
    assert supplemental["status"] == "COMPLETED"
    return supplemental


def test_review_request_is_empty_before_creation(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/assessment/review-request")

    assert response.status_code == 200
    assert response.json() == {"sessionId": session_id, "reviewRequest": None}


def test_review_request_requires_a_completed_assessment(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/assessment/review-request")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSESSMENT_REVIEW_TARGET_NOT_READY"


def test_customer_can_request_idempotent_baseline_review(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    assessment = run_baseline(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    endpoint = f"/v1/sessions/{session_id}/assessment/review-request"

    first = client.post(endpoint)
    second = client.post(endpoint)
    stored = client.get(endpoint)

    assert first.status_code == 200
    assert second.json() == first.json()
    assert stored.json() == first.json()
    review = first.json()["reviewRequest"]
    assert review["reviewRequestId"].startswith("arr_")
    assert review["targetType"] == "BASELINE_ASSESSMENT"
    assert review["targetAssessmentId"] == assessment["assessmentId"]
    assert review["reasonCode"] == "CUSTOMER_REQUESTED_ASSESSMENT_REVIEW"
    assert review["requestedAt"].endswith("Z")
    assert len(review["requestSnapshotHash"]) == 64
    assert review["dataVersion"]
    assert review["modelVersion"] == assessment["modelVersion"]
    assert review["requestPolicyVersion"] == "assessment-review-request-policy-v1"
    assert review["demoOnly"] is True
    events = [
        event
        for event in session_repository.list_audit_events(session_id)
        if event.stage == AuditStage.ASSESSMENT_REVIEW_REQUESTED
    ]
    assert len(events) == 1
    assert events[0].actor == AuditActor.CUSTOMER
    assert events[0].input_version == assessment["assessmentId"]


def test_latest_completed_supplemental_assessment_becomes_review_target(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
) -> None:
    session_id = create_session(client)
    run_baseline(client, session_id, data_source_service, assessment_service)
    supplemental = run_supplemental(
        client,
        session_id,
        supplemental_assessment_service,
    )

    response = client.post(f"/v1/sessions/{session_id}/assessment/review-request")

    assert response.status_code == 200
    review = response.json()["reviewRequest"]
    assert review["targetType"] == "SUPPLEMENTAL_ASSESSMENT"
    assert review["targetAssessmentId"] == supplemental["supplementalAssessmentId"]
    assert review["modelVersion"] == supplemental["modelVersion"]


def test_customer_review_request_appears_in_admin_queue_without_snapshot_hash(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    assessment = run_baseline(
        client,
        session_id,
        data_source_service,
        assessment_service,
    )
    request_response = client.post(f"/v1/sessions/{session_id}/assessment/review-request")
    review = request_response.json()["reviewRequest"]

    queue_response = client.get(
        "/v1/admin/underwriter-reviews",
        headers=ADMIN_HEADERS,
    )

    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert queue["totalCount"] == 1
    assert queue["items"] == [
        {
            "reviewId": f"uwr_{review['reviewRequestId'].removeprefix('arr_')}",
            "sessionId": session_id,
            "triggerType": "CUSTOMER_ASSESSMENT_REVIEW",
            "triggerId": review["reviewRequestId"],
            "targetType": "BASELINE_ASSESSMENT",
            "targetAssessmentId": assessment["assessmentId"],
            "reasonCodes": ["CUSTOMER_REQUESTED_ASSESSMENT_REVIEW"],
            "requestedAt": review["requestedAt"],
            "dataVersion": review["dataVersion"],
            "policyVersion": "assessment-review-request-policy-v1",
            "demoOnly": True,
        }
    ]
    assert "requestSnapshotHash" not in queue_response.text
