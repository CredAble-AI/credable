from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.main as main_module
from app.core.config import Settings

ADMIN_HEADERS = {"X-Admin-API-Key": "recovery-test-admin-key"}


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
    review_request = assert_ok(client.post(f"/v1/sessions/{session_id}/assessment/review-request"))
    review_id = "uwr_" + review_request["reviewRequest"]["reviewRequestId"].removeprefix("arr_")
    assert_ok(
        client.post(
            f"/v1/admin/underwriter-reviews/{review_id}/claim",
            headers=ADMIN_HEADERS,
        )
    )
    recovered["underwriterReview"] = assert_ok(
        client.post(
            f"/v1/admin/underwriter-reviews/{review_id}/complete",
            headers=ADMIN_HEADERS,
            json={"resultCode": "ASSESSMENT_CONFIRMED"},
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
            headers=ADMIN_HEADERS,
        )
    )
    recovered["burden"] = assert_ok(
        client.get(
            f"/v1/admin/sessions/{session_id}/evidence-burden",
            headers=ADMIN_HEADERS,
        )
    )
    recovered["underwriterReviews"] = assert_ok(
        client.get("/v1/admin/underwriter-reviews", headers=ADMIN_HEADERS)
    )
    return session_id, submission_id, recovered


def test_complete_journey_is_restored_after_application_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "recovery.db"
    test_settings = Settings(
        database_path=database_path,
        admin_api_key=SecretStr(ADMIN_HEADERS["X-Admin-API-Key"]),
    )
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
                    headers=ADMIN_HEADERS,
                )
            ),
            "underwriterReview": assert_ok(
                restarted_client.get(
                    f"/v1/admin/underwriter-reviews/{review_id}",
                    headers=ADMIN_HEADERS,
                )
            ),
            "burden": assert_ok(
                restarted_client.get(
                    f"/v1/admin/sessions/{session_id}/evidence-burden",
                    headers=ADMIN_HEADERS,
                )
            ),
            "underwriterReviews": assert_ok(
                restarted_client.get(
                    "/v1/admin/underwriter-reviews",
                    headers=ADMIN_HEADERS,
                )
            ),
        }

    assert expected["productComparison"].pop("assembledAt").endswith("Z")
    assert actual["productComparison"].pop("assembledAt").endswith("Z")
    assert actual == expected
