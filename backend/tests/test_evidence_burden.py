from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    DemoAssessmentAdapter,
    DemoSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService, SupplementalAssessmentService
from app.services.data_source_service import DataSourceService


def create_session(client: TestClient) -> dict:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "small-business"},
    )
    assert response.status_code == 201
    return response.json()["session"]


def test_admin_evidence_burden_returns_policy_neutral_empty_metrics(
    client: TestClient,
) -> None:
    session = create_session(client)

    response = client.get(
        f"/v1/admin/sessions/{session['sessionId']}/evidence-burden",
    )

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": session["sessionId"],
        "asOf": session["createdAt"],
        "evidenceRequestCount": 0,
        "repeatedRequestCount": 0,
        "availableRequestCount": 0,
        "requestableRequestCount": 0,
        "consentRequiredRequestCount": 0,
        "unavailableRequestCount": 0,
        "submissionCount": 0,
        "pendingSubmissionCount": 0,
        "acceptedCount": 0,
        "rejectedCount": 0,
        "reviewRequiredCount": 0,
        "unverifiedSubmissionCount": 0,
        "failedQualityDimensionCount": 0,
        "supplementalAssessmentCount": 0,
        "resolutionCount": 0,
        "latestResolutionStatus": None,
        "collectionStopped": None,
        "maxRequestIteration": 0,
        "evidenceTypes": [],
        "measurementVersion": "evidence-burden-metrics-v1",
        "policyThresholdApplied": False,
        "demoOnly": True,
    }


def test_admin_evidence_burden_aggregates_verified_session_history(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
) -> None:
    session = create_session(client)
    session_id = session["sessionId"]
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        settings.demo_supplemental_assessments_path
    )
    for source_type in (
        ConsentSourceType.BANK_INTERNAL,
        ConsentSourceType.CREDIT_INFORMATION,
    ):
        assert (
            client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant").status_code
            == 200
        )
    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/run").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/boundary-check").status_code == 200
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
    assert quality_response.json()["quality"]["status"] == "ACCEPTED"
    supplemental_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json={"submissionId": submission["submissionId"]},
    )
    assert supplemental_response.status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/comparison").status_code == 200
    resolution_response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")
    assert resolution_response.status_code == 200
    resolution = resolution_response.json()["resolution"]

    response = client.get(
        f"/v1/admin/sessions/{session_id}/evidence-burden",
    )

    assert response.status_code == 200
    burden = response.json()
    assert burden["sessionId"] == session_id
    assert burden["asOf"] == resolution["resolvedAt"]
    assert burden["evidenceRequestCount"] == 1
    assert burden["repeatedRequestCount"] == 0
    assert burden["availableRequestCount"] == 0
    assert burden["requestableRequestCount"] == 0
    assert burden["consentRequiredRequestCount"] == 1
    assert burden["unavailableRequestCount"] == 0
    assert burden["submissionCount"] == 1
    assert burden["pendingSubmissionCount"] == 0
    assert burden["acceptedCount"] == 1
    assert burden["rejectedCount"] == 0
    assert burden["reviewRequiredCount"] == 0
    assert burden["unverifiedSubmissionCount"] == 0
    assert burden["failedQualityDimensionCount"] == 0
    assert burden["supplementalAssessmentCount"] == 1
    assert burden["resolutionCount"] == 1
    assert burden["latestResolutionStatus"] == "RESOLVED"
    assert burden["collectionStopped"] is True
    assert burden["maxRequestIteration"] == 1
    assert burden["measurementVersion"] == "evidence-burden-metrics-v1"
    assert burden["policyThresholdApplied"] is False
    assert burden["demoOnly"] is True
    assert burden["evidenceTypes"] == [
        {
            "evidenceType": "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY",
            "sourceType": "CUSTOMER_SUBMITTED",
            "requestCount": 1,
            "submissionCount": 1,
            "acceptedCount": 1,
            "rejectedCount": 0,
            "reviewRequiredCount": 0,
            "firstRequestedAt": selection["selectedAt"],
            "lastRequestedAt": selection["selectedAt"],
        }
    ]
    assert "sourceReference" not in response.text
    assert "evidenceValue" not in response.text
