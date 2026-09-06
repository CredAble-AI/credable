from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import DemoAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService

ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-api-key"}


def create_suspicious_quality(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> tuple[str, dict]:
    session_response = client.post(
        "/v1/sessions/demo",
        json={"businessBorrowerType": "SOLE_PROPRIETOR"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["sessionId"]
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
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
    selection_id = selection_response.json()["selection"]["selectionId"]
    consent_response = client.post(
        f"/v1/sessions/{session_id}/evidence/selections/{selection_id}/consent/grant"
    )
    assert consent_response.status_code == 200
    upload_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/upload",
        data={"selectionId": selection_id},
        files={
            "file": (
                "changed-demo.pdf",
                b"%PDF-1.4\nchanged review queue evidence\n%%EOF",
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 200
    submission_id = upload_response.json()["submission"]["submissionId"]
    quality_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission_id}/quality"
    )
    assert quality_response.status_code == 200
    quality = quality_response.json()["quality"]
    assert quality["status"] == "REVIEW_REQUIRED"
    return session_id, quality


def test_underwriter_review_queue_requires_admin_authentication(client: TestClient) -> None:
    response = client.get("/v1/admin/underwriter-reviews")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ADMIN_AUTHENTICATION_FAILED"


def test_underwriter_review_queue_is_empty_without_suspicious_quality(
    client: TestClient,
) -> None:
    response = client.get("/v1/admin/underwriter-reviews", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "totalCount": 0,
        "limit": 50,
        "offset": 0,
        "items": [],
        "demoOnly": True,
    }


def test_underwriter_review_queue_exposes_only_safe_review_context(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id, quality = create_suspicious_quality(
        client,
        data_source_service,
        assessment_service,
    )

    response = client.get("/v1/admin/underwriter-reviews", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["totalCount"] == 1
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert payload["items"] == [
        {
            "reviewId": f"uwr_{quality['qualityCheckId'].removeprefix('evq_')}",
            "sessionId": session_id,
            "triggerType": "EVIDENCE_QUALITY",
            "triggerId": quality["qualityCheckId"],
            "evidenceType": quality["evidenceType"],
            "reasonCodes": quality["suspicionCodes"],
            "requestedAt": quality["checkedAt"],
            "dataVersion": quality["dataVersion"],
            "policyVersion": quality["qualityPolicyVersion"],
            "status": "PENDING",
            "demoOnly": True,
        }
    ]
    assert "sha256" not in response.text.lower()
    assert "changed review queue evidence" not in response.text


def test_underwriter_review_queue_supports_bounded_offset_paging(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    first_session_id, _ = create_suspicious_quality(
        client,
        data_source_service,
        assessment_service,
    )
    second_session_id, _ = create_suspicious_quality(
        client,
        data_source_service,
        assessment_service,
    )

    first_page = client.get(
        "/v1/admin/underwriter-reviews?limit=1&offset=0",
        headers=ADMIN_HEADERS,
    )
    second_page = client.get(
        "/v1/admin/underwriter-reviews?limit=1&offset=1",
        headers=ADMIN_HEADERS,
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert first_page.json()["totalCount"] == 2
    assert second_page.json()["totalCount"] == 2
    assert first_page.json()["items"][0]["sessionId"] == second_session_id
    assert second_page.json()["items"][0]["sessionId"] == first_session_id


def test_underwriter_review_queue_rejects_unbounded_page_parameters(
    client: TestClient,
) -> None:
    too_large = client.get(
        "/v1/admin/underwriter-reviews?limit=101",
        headers=ADMIN_HEADERS,
    )
    negative_offset = client.get(
        "/v1/admin/underwriter-reviews?offset=-1",
        headers=ADMIN_HEADERS,
    )

    assert too_large.status_code == 422
    assert negative_offset.status_code == 422


def test_underwriter_review_queue_allows_offset_past_last_item(
    client: TestClient,
) -> None:
    response = client.get(
        "/v1/admin/underwriter-reviews?offset=999",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["totalCount"] == 0
    assert response.json()["offset"] == 999
    assert response.json()["items"] == []


def test_evidence_review_accepts_only_evidence_result_codes(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    _, quality = create_suspicious_quality(
        client,
        data_source_service,
        assessment_service,
    )
    review_id = f"uwr_{quality['qualityCheckId'].removeprefix('evq_')}"
    endpoint = f"/v1/admin/underwriter-reviews/{review_id}"

    claimed = client.post(f"{endpoint}/claim", headers=ADMIN_HEADERS)
    invalid = client.post(
        f"{endpoint}/complete",
        headers=ADMIN_HEADERS,
        json={"resultCode": "ASSESSMENT_CONFIRMED"},
    )
    completed = client.post(
        f"{endpoint}/complete",
        headers=ADMIN_HEADERS,
        json={"resultCode": "EVIDENCE_EXCLUDED"},
    )

    assert claimed.status_code == 200
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "UNDERWRITER_REVIEW_RESULT_NOT_ALLOWED"
    assert completed.status_code == 200
    assert completed.json()["review"]["status"] == "COMPLETED"
    assert completed.json()["review"]["resultCode"] == "EVIDENCE_EXCLUDED"
