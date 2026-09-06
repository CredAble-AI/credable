from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import Settings

REVIEW_REQUEST_BODY = {"customerReasonCode": "MISSING_RECENT_INFORMATION"}


def assert_ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def execute_complete_journey(client: TestClient) -> tuple[str, str, dict[str, dict]]:
    created = client.post("/v1/sessions/demo", json={"demoProfileId": "small-business"})
    assert created.status_code == 201
    session_id = created.json()["sessionId"]

    for source_type in ("BANK_INTERNAL", "CREDIT_INFORMATION"):
        assert_ok(client.post(f"/v1/sessions/{session_id}/consents/{source_type}/grant"))

    recovered: dict[str, dict] = {
        "session": {"session": created.json()["session"]},
        "consents": assert_ok(client.get(f"/v1/sessions/{session_id}/consents")),
        "dataSources": assert_ok(client.post(f"/v1/sessions/{session_id}/data-sources/refresh")),
        "assessment": assert_ok(client.post(f"/v1/sessions/{session_id}/assessment/run")),
    }
    assert recovered["assessment"]["assessment"]["status"] == "COMPLETED"

    recovered["boundary"] = assert_ok(
        client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")
    )
    recovered["selection"] = assert_ok(client.post(f"/v1/sessions/{session_id}/evidence/next"))
    selection_id = recovered["selection"]["selection"]["selectionId"]
    recovered["submission"] = assert_ok(
        client.post(
            f"/v1/sessions/{session_id}/evidence/submissions",
            json={
                "selectionId": selection_id,
                "submissionMode": "DEMO_FIXTURE_REFERENCE",
            },
        )
    )
    submission_id = recovered["submission"]["submission"]["submissionId"]
    recovered["quality"] = assert_ok(
        client.post(f"/v1/sessions/{session_id}/evidence/submissions/{submission_id}/quality")
    )
    recovered["supplemental"] = assert_ok(
        client.post(
            f"/v1/sessions/{session_id}/assessment/supplemental/run",
            json={"submissionId": submission_id},
        )
    )
    recovered["assessmentComparison"] = assert_ok(
        client.post(f"/v1/sessions/{session_id}/assessment/comparison")
    )
    recovered["resolution"] = assert_ok(
        client.post(f"/v1/sessions/{session_id}/assessment/resolution")
    )
    recovered["explanation"] = assert_ok(
        client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")
    )
    review_request = assert_ok(
        client.post(
            f"/v1/sessions/{session_id}/assessment/review-request",
            json=REVIEW_REQUEST_BODY,
        )
    )
    review_id = review_request["underwriterReviewId"]
    assert_ok(
        client.post(
            f"/v1/admin/underwriter-reviews/{review_id}/claim",
        )
    )
    recovered["underwriterReview"] = assert_ok(
        client.post(
            f"/v1/admin/underwriter-reviews/{review_id}/complete",
            json={
                "resultCode": "ASSESSMENT_CONFIRMED",
                "decisionNote": "합성 시연 데이터로 판단 근거를 확인했습니다.",
            },
        )
    )
    recovered["assessmentReviewRequest"] = assert_ok(
        client.get(f"/v1/sessions/{session_id}/assessment/review-request")
    )
    recovered["products"] = assert_ok(client.post(f"/v1/sessions/{session_id}/products/refresh"))
    recovered["productConditions"] = assert_ok(
        client.post(f"/v1/sessions/{session_id}/product-conditions/query")
    )
    recovered["productComparison"] = assert_ok(client.get(f"/v1/sessions/{session_id}/comparison"))
    recovered["audit"] = assert_ok(
        client.get(
            f"/v1/admin/sessions/{session_id}/audit-events",
            params={"limit": 100},
        )
    )
    recovered["burden"] = assert_ok(client.get(f"/v1/admin/sessions/{session_id}/evidence-burden"))
    recovered["underwriterReviews"] = assert_ok(client.get("/v1/admin/underwriter-reviews"))
    return session_id, submission_id, recovered


def test_complete_journey_is_restored_after_application_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "recovery.db"
    test_settings = Settings(database_path=database_path)
    monkeypatch.setattr(main_module, "settings", test_settings)

    with TestClient(main_module.create_app()) as client:
        assert assert_ok(client.get("/ready"))["status"] == "ready"
        session_id, submission_id, expected = execute_complete_journey(client)
        review_id = expected["underwriterReview"]["review"]["reviewId"]

    assert database_path.is_file()

    with TestClient(main_module.create_app()) as restarted_client:
        assert assert_ok(restarted_client.get("/ready"))["status"] == "ready"
        actual = {
            "session": assert_ok(restarted_client.get(f"/v1/sessions/{session_id}")),
            "consents": assert_ok(restarted_client.get(f"/v1/sessions/{session_id}/consents")),
            "dataSources": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/data-sources")
            ),
            "assessment": assert_ok(restarted_client.get(f"/v1/sessions/{session_id}/assessment")),
            "boundary": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/assessment/boundary-check")
            ),
            "selection": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/evidence/next")
            ),
            "submission": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/evidence/submissions/latest")
            ),
            "quality": assert_ok(
                restarted_client.get(
                    f"/v1/sessions/{session_id}/evidence/submissions/{submission_id}/quality"
                )
            ),
            "supplemental": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/assessment/supplemental")
            ),
            "assessmentComparison": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/assessment/comparison")
            ),
            "resolution": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/assessment/resolution")
            ),
            "explanation": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/assessment/explanation")
            ),
            "assessmentReviewRequest": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/assessment/review-request")
            ),
            "products": assert_ok(restarted_client.get(f"/v1/sessions/{session_id}/products")),
            "productConditions": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/product-conditions")
            ),
            "productComparison": assert_ok(
                restarted_client.get(f"/v1/sessions/{session_id}/comparison")
            ),
            "audit": assert_ok(
                restarted_client.get(
                    f"/v1/admin/sessions/{session_id}/audit-events",
                    params={"limit": 100},
                )
            ),
            "underwriterReview": assert_ok(
                restarted_client.get(
                    f"/v1/admin/underwriter-reviews/{review_id}",
                )
            ),
            "burden": assert_ok(
                restarted_client.get(
                    f"/v1/admin/sessions/{session_id}/evidence-burden",
                )
            ),
            "underwriterReviews": assert_ok(
                restarted_client.get(
                    "/v1/admin/underwriter-reviews",
                )
            ),
        }

    assert expected["productComparison"].pop("assembledAt").endswith("Z")
    assert actual["productComparison"].pop("assembledAt").endswith("Z")
    assert actual == expected
