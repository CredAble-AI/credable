from fastapi.testclient import TestClient

from app.repositories.consent_repository import SqliteConsentRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType


def create_session(client: TestClient) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "small-business"},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def test_list_consents_starts_pending_without_assuming_requirement(
    client: TestClient,
) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/consents")

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == session_id
    assert body["scopeVersion"] == "demo-consent-scopes-v1"
    assert body["demoOnly"] is True
    assert [item["sourceType"] for item in body["consents"]] == [
        "BANK_INTERNAL",
        "CREDIT_INFORMATION",
        "CUSTOMER_SUBMITTED",
        "EXTERNAL_CONNECTED",
    ]
    for consent in body["consents"]:
        assert consent["required"] is None
        assert consent["status"] == "PENDING"
        assert consent["grantedAt"] is None
        assert consent["withdrawnAt"] is None
        assert consent["updatedAt"] is None
        assert consent["demoOnly"] is True


def test_grant_consent_persists_state_and_audit(
    client: TestClient,
    consent_repository: SqliteConsentRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/consents/BANK_INTERNAL/grant")

    assert response.status_code == 200
    granted = response.json()
    assert granted["sourceType"] == "BANK_INTERNAL"
    assert granted["status"] == "GRANTED"
    assert granted["required"] is None
    assert granted["grantedAt"].endswith("Z")
    assert granted["withdrawnAt"] is None
    assert granted["updatedAt"] == granted["grantedAt"]

    reopened = SqliteConsentRepository(consent_repository.database_path)
    reopened.initialize()
    stored = reopened.get_consent(session_id, ConsentSourceType.BANK_INTERNAL)
    assert stored is not None
    assert stored.model_dump(mode="json", by_alias=True) == granted

    events = session_repository.list_audit_events(session_id)
    assert [event.stage for event in events] == [
        AuditStage.SESSION_CREATED,
        AuditStage.CONSENT_GRANTED,
    ]
    assert events[-1].output_summary == {
        "sourceType": "BANK_INTERNAL",
        "status": "GRANTED",
        "demoOnly": True,
    }
    assert events[-1].request_id == response.headers["X-Request-ID"]


def test_grant_is_idempotent_and_withdrawal_is_audited(
    client: TestClient,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    route = f"/v1/sessions/{session_id}/consents/CREDIT_INFORMATION"

    first_grant = client.post(f"{route}/grant")
    second_grant = client.post(f"{route}/grant")
    withdrawal = client.post(f"{route}/withdraw")
    repeated_withdrawal = client.post(f"{route}/withdraw")

    assert first_grant.status_code == 200
    assert second_grant.json() == first_grant.json()
    assert withdrawal.status_code == 200
    assert withdrawal.json()["status"] == "WITHDRAWN"
    assert withdrawal.json()["grantedAt"] == first_grant.json()["grantedAt"]
    assert withdrawal.json()["withdrawnAt"].endswith("Z")
    assert repeated_withdrawal.json() == withdrawal.json()

    events = session_repository.list_audit_events(session_id)
    assert [event.stage for event in events] == [
        AuditStage.SESSION_CREATED,
        AuditStage.CONSENT_GRANTED,
        AuditStage.CONSENT_WITHDRAWN,
    ]


def test_list_consents_combines_stored_and_pending_states(client: TestClient) -> None:
    session_id = create_session(client)
    client.post(f"/v1/sessions/{session_id}/consents/CUSTOMER_SUBMITTED/grant")

    response = client.get(f"/v1/sessions/{session_id}/consents")

    statuses = {item["sourceType"]: item["status"] for item in response.json()["consents"]}
    assert statuses == {
        "BANK_INTERNAL": "PENDING",
        "CREDIT_INFORMATION": "PENDING",
        "CUSTOMER_SUBMITTED": "GRANTED",
        "EXTERNAL_CONNECTED": "PENDING",
    }


def test_withdrawal_requires_a_granted_consent(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/consents/EXTERNAL_CONNECTED/withdraw")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSENT_NOT_GRANTED"
    assert response.json()["error"]["retryable"] is False


def test_unknown_session_and_scope_use_standard_errors(client: TestClient) -> None:
    missing_session = client.get("/v1/sessions/ses_missing/consents")
    assert missing_session.status_code == 404
    assert missing_session.json()["error"]["code"] == "CUSTOMER_SESSION_NOT_FOUND"

    session_id = create_session(client)
    missing_scope = client.post(f"/v1/sessions/{session_id}/consents/UNKNOWN/grant")
    assert missing_scope.status_code == 404
    assert missing_scope.json()["error"]["code"] == "CONSENT_SCOPE_NOT_FOUND"
