import pytest
from fastapi.testclient import TestClient


def create_demo_session(client: TestClient) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "small-business"},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def test_admin_can_page_session_audit_events_without_raw_financial_data(
    client: TestClient,
) -> None:
    session_id = create_demo_session(client)
    first_consent = client.post(f"/v1/sessions/{session_id}/consents/BANK_INTERNAL/grant")
    second_consent = client.post(f"/v1/sessions/{session_id}/consents/CREDIT_INFORMATION/grant")
    assert first_consent.status_code == 200
    assert second_consent.status_code == 200

    first_page = client.get(
        f"/v1/admin/sessions/{session_id}/audit-events",
        params={"limit": 2},
    )

    assert first_page.status_code == 200
    body = first_page.json()
    assert body["sessionId"] == session_id
    assert body["demoOnly"] is True
    assert [event["stage"] for event in body["events"]] == [
        "CONSENT_GRANTED",
        "CONSENT_GRANTED",
    ]
    assert {event["outputSummary"]["sourceType"] for event in body["events"]} == {
        "BANK_INTERNAL",
        "CREDIT_INFORMATION",
    }
    timestamps = [event["timestamp"] for event in body["events"]]
    assert timestamps == sorted(timestamps, reverse=True)
    assert body["nextCursor"] is not None
    assert set(body["events"][0]) == {
        "eventId",
        "sessionId",
        "requestId",
        "stage",
        "timestamp",
        "actor",
        "inputVersion",
        "inputSnapshotHash",
        "outputSummary",
        "dataVersion",
        "modelVersion",
        "policyVersion",
    }

    second_page = client.get(
        f"/v1/admin/sessions/{session_id}/audit-events",
        params={"limit": 2, "cursor": body["nextCursor"]},
    )

    assert second_page.status_code == 200
    second_body = second_page.json()
    assert [event["stage"] for event in second_body["events"]] == ["SESSION_CREATED"]
    assert second_body["nextCursor"] is None
    first_ids = {event["eventId"] for event in body["events"]}
    second_ids = {event["eventId"] for event in second_body["events"]}
    assert first_ids.isdisjoint(second_ids)


def test_admin_audit_rejects_invalid_cursor(client: TestClient) -> None:
    session_id = create_demo_session(client)

    response = client.get(
        f"/v1/admin/sessions/{session_id}/audit-events",
        params={"cursor": "not-a-valid-cursor"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_AUDIT_CURSOR"


def test_admin_audit_uses_session_not_found_contract(client: TestClient) -> None:
    response = client.get("/v1/admin/sessions/ses_does_not_exist/audit-events")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_SESSION_NOT_FOUND"


@pytest.mark.parametrize("limit", [0, 101])
def test_admin_audit_rejects_out_of_range_limit(client: TestClient, limit: int) -> None:
    response = client.get(
        "/v1/admin/sessions/ses_unknown/audit-events",
        params={"limit": limit},
    )

    assert response.status_code == 422
