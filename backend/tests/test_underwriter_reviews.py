import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import DemoAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService
from app.services.evidence_selection_service import (
    DemoEvidenceCandidateCatalog,
    EvidenceSelectionService,
)
from app.services.policy_boundary_service import (
    DemoPolicyBoundaryCatalog,
    PolicyBoundaryService,
)


def create_completed_assessment(
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
    assessment_response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    assert assessment_response.status_code == 200
    assert assessment_response.json()["assessment"]["status"] == "COMPLETED"
    return session_id, assessment_response.json()["assessment"]


def create_suspicious_quality(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> tuple[str, dict]:
    session_id, _ = create_completed_assessment(
        client,
        data_source_service,
        assessment_service,
    )
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


def get_only_review(client: TestClient) -> dict:
    response = client.get("/v1/admin/underwriter-reviews")
    assert response.status_code == 200
    assert response.json()["totalCount"] == 1
    return response.json()["items"][0]


def test_underwriter_review_queue_is_empty_without_suspicious_quality(
    client: TestClient,
) -> None:
    response = client.get("/v1/admin/underwriter-reviews")

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

    response = client.get("/v1/admin/underwriter-reviews")

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

    detail_response = client.get(f"/v1/admin/underwriter-reviews/{payload['items'][0]['reviewId']}")
    assert detail_response.status_code == 200
    context = detail_response.json()["context"]
    assert context["assessment"] is not None
    assert context["boundaryCheck"] is not None
    assert context["submission"]["submissionId"] == quality["submissionId"]
    assert context["submission"]["uploadedFile"]["fileName"] == "changed-demo.pdf"
    assert context["quality"]["qualityCheckId"] == quality["qualityCheckId"]
    assert len(context["quality"]["checks"]) == 6
    assert "supplementalAssessment" not in context
    assert "comparison" not in context


def test_policy_blocked_boundary_is_exposed_in_underwriter_queue(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    policy_boundary_service: PolicyBoundaryService,
    tmp_path: Path,
) -> None:
    session_id, assessment = create_completed_assessment(
        client,
        data_source_service,
        assessment_service,
    )
    catalog_path = tmp_path / "blocked-policy.json"
    catalog_path.write_text(
        json.dumps(
            {
                "dataVersion": "test-blocked-policy-v1",
                "policyVersion": "test-blocked-policy-v1",
                "gradeRoutes": [{"grade": "DEMO_GRADE_B", "route": "DEMO_PATH_1"}],
                "boundaries": [],
                "demoOnly": True,
            }
        ),
        encoding="utf-8",
    )
    policy_boundary_service.catalog = DemoPolicyBoundaryCatalog(catalog_path)
    boundary_response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")
    assert boundary_response.status_code == 200
    boundary = boundary_response.json()["boundaryCheck"]
    assert boundary["decision"]["status"] == "POLICY_BLOCKED"

    review = get_only_review(client)

    assert review["triggerType"] == "POLICY_BOUNDARY"
    assert review["triggerId"] == boundary["boundaryCheckId"]
    assert review["reasonCodes"] == ["DEMO_GRADE_POLICY_NOT_CONFIGURED"]
    assert review["dataVersion"] == assessment["inputSnapshotId"]
    assert review["policyVersion"] == "test-blocked-policy-v1"
    endpoint = f"/v1/admin/underwriter-reviews/{review['reviewId']}"
    assert client.post(f"{endpoint}/claim").status_code == 200
    completed = client.post(
        f"{endpoint}/complete",
        json={"resultCode": "ASSESSMENT_CONFIRMED"},
    )
    assert completed.status_code == 200
    assert completed.json()["review"]["status"] == "COMPLETED"


def test_terminal_evidence_selection_is_exposed_in_underwriter_queue(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_selection_service: EvidenceSelectionService,
    tmp_path: Path,
) -> None:
    session_id, assessment = create_completed_assessment(
        client,
        data_source_service,
        assessment_service,
    )
    boundary_response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")
    assert boundary_response.status_code == 200
    catalog_data = json.loads(settings.demo_evidence_candidates_path.read_text(encoding="utf-8"))
    catalog_data["candidates"] = [catalog_data["candidates"][0]]
    catalog_data["candidates"][0]["informationContentCodes"] = ["BANK_CASH_FLOW_TOTALS"]
    catalog_path = tmp_path / "overlapping-evidence.json"
    catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")
    evidence_selection_service.catalog = DemoEvidenceCandidateCatalog(catalog_path)
    selection_response = client.post(f"/v1/sessions/{session_id}/evidence/next")
    assert selection_response.status_code == 200
    selection = selection_response.json()["selection"]
    assert selection["status"] == "HUMAN_REVIEW"

    review = get_only_review(client)

    assert review["triggerType"] == "EVIDENCE_SELECTION"
    assert review["triggerId"] == selection["selectionId"]
    assert review["reasonCodes"] == ["NO_NOVEL_EVIDENCE"]
    assert review["dataVersion"] == assessment["inputSnapshotId"]
    assert review["policyVersion"] == "demo-novel-evidence-selection-v4"


def test_human_review_resolution_is_exposed_in_underwriter_queue(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id, _ = create_completed_assessment(
        client,
        data_source_service,
        assessment_service,
    )
    assert client.post(f"/v1/sessions/{session_id}/assessment/boundary-check").status_code == 200
    selection = client.post(f"/v1/sessions/{session_id}/evidence/next").json()["selection"]
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
    supplemental_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json={"submissionId": submission["submissionId"]},
    )
    assert supplemental_response.status_code == 200
    supplemental = supplemental_response.json()["supplementalAssessment"]
    assert supplemental["status"] == "MODEL_NOT_CONFIGURED"
    assert client.post(f"/v1/sessions/{session_id}/assessment/comparison").status_code == 200
    resolution_response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")
    assert resolution_response.status_code == 200
    resolution = resolution_response.json()["resolution"]
    assert resolution["status"] == "HUMAN_REVIEW"

    review = get_only_review(client)

    assert review["triggerType"] == "EVIDENCE_RESOLUTION"
    assert review["triggerId"] == resolution["resolutionId"]
    assert review["reasonCodes"] == ["UNCERTAINTY_COMPARISON_NOT_RELIABLE"]
    assert review["dataVersion"] == supplemental["supplementalAssessmentId"]
    assert review["policyVersion"] == "demo-policy-boundary-v2"


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
    )
    second_page = client.get(
        "/v1/admin/underwriter-reviews?limit=1&offset=1",
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
    )
    negative_offset = client.get(
        "/v1/admin/underwriter-reviews?offset=-1",
    )

    assert too_large.status_code == 422
    assert negative_offset.status_code == 422


def test_underwriter_review_queue_allows_offset_past_last_item(
    client: TestClient,
) -> None:
    response = client.get("/v1/admin/underwriter-reviews?offset=999")

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

    claimed = client.post(f"{endpoint}/claim")
    invalid = client.post(
        f"{endpoint}/complete",
        json={"resultCode": "ASSESSMENT_CONFIRMED"},
    )
    completed = client.post(
        f"{endpoint}/complete",
        json={"resultCode": "EVIDENCE_EXCLUDED"},
    )

    assert claimed.status_code == 200
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "UNDERWRITER_REVIEW_RESULT_NOT_ALLOWED"
    assert completed.status_code == 200
    assert completed.json()["review"]["status"] == "COMPLETED"
    assert completed.json()["review"]["resultCode"] == "EVIDENCE_EXCLUDED"
