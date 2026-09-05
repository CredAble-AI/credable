from fastapi.testclient import TestClient

from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.session import CustomerSession
from app.services.session_service import CustomerSessionService


def test_create_and_restore_small_business_demo_session(
    client: TestClient,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    create_response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "small-business"},
    )

    assert create_response.status_code == 201
    assert create_response.headers["X-Request-ID"].startswith("req_")
    created = create_response.json()
    assert created["sessionId"].startswith("ses_")
    assert created["session"]["sessionId"] == created["sessionId"]
    assert set(created["session"]) == {
        "sessionId",
        "demoProfile",
        "customerSubject",
        "status",
        "createdAt",
        "dataVersion",
        "demoOnly",
    }
    assert created["session"]["demoProfile"] == {
        "demoProfileId": "small-business",
        "businessBorrowerType": "SOLE_PROPRIETOR",
        "displayName": "개인사업자",
        "description": "개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례",
    }
    assert created["session"]["customerSubject"] == {
        "borrower": {
            "borrowerId": "bor_demo_001",
            "borrowerType": "SOLE_PROPRIETOR",
            "displayName": "도담상점 고객(합성)",
        },
        "primaryBusiness": {
            "businessId": "biz_demo_001",
            "legalForm": "SOLE_PROPRIETOR",
            "displayName": "도담상점(합성)",
            "industryCode": "DEMO_RETAIL",
            "industryCodeSystem": "DEMO",
            "industryName": "소매업 예시",
            "businessStartedOn": "2022-04-15",
            "status": "ACTIVE",
        },
        "businessRole": {
            "borrowerId": "bor_demo_001",
            "businessId": "biz_demo_001",
            "roleType": "OWNER",
            "isPrimary": True,
            "effectiveFrom": "2022-04-15",
            "effectiveTo": None,
        },
        "sourceType": "BANK_INTERNAL",
        "asOfDate": "2026-09-01",
        "dataVersion": "demo-customer-subjects-v1",
        "demoOnly": True,
    }
    assert created["session"]["status"] == "CREATED"
    assert created["session"]["dataVersion"] == "demo-profiles-v3"
    assert created["session"]["demoOnly"] is True
    assert created["session"]["createdAt"].endswith("Z")

    legacy_session = created["session"].copy()
    legacy_session.pop("customerSubject")
    legacy_session["demoProfile"] = legacy_session["demoProfile"].copy()
    legacy_session["demoProfile"].pop("businessBorrowerType")
    restored_legacy_session = CustomerSession.model_validate(legacy_session)
    assert restored_legacy_session.customer_subject is None
    assert restored_legacy_session.demo_profile.business_borrower_type is None

    session_id = created["sessionId"]
    get_response = client.get(f"/v1/sessions/{session_id}")

    assert get_response.status_code == 200
    assert get_response.json() == {"session": created["session"]}

    reopened_repository = SqliteCustomerSessionRepository(session_repository.database_path)
    reopened_repository.initialize()
    stored = reopened_repository.get_session(session_id)
    original = session_repository.get_session(session_id)
    assert stored is not None
    assert original is not None
    assert stored.session == original.session
    assert reopened_repository.get_customer_subject(session_id) == stored.session.customer_subject

    events = session_repository.list_audit_events(session_id)
    assert len(events) == 1
    assert events[0].request_id == create_response.headers["X-Request-ID"]


def test_same_demo_profile_creates_a_fresh_session_each_time(
    client: TestClient,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    first = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "startup"},
    )
    second = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "startup"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["sessionId"] != second.json()["sessionId"]

    first_events = session_repository.list_audit_events(first.json()["sessionId"])
    second_events = session_repository.list_audit_events(second.json()["sessionId"])
    assert len(first_events) == 1
    assert len(second_events) == 1
    assert first_events[0].stage == AuditStage.SESSION_CREATED
    assert first_events[0].input_version == "demo-profiles-v3"
    assert first_events[0].output_summary == {
        "demoProfileId": "startup",
        "businessBorrowerType": "CORPORATION",
        "borrowerId": "bor_demo_002",
        "primaryBusinessId": "biz_demo_002",
        "demoOnly": True,
    }
    assert len(first_events[0].input_snapshot_hash) == 64
    assert session_repository.get_customer_subject(first.json()["sessionId"]) == (
        session_repository.get_customer_subject(second.json()["sessionId"])
    )


def test_catalog_contains_only_approved_demo_profiles(
    session_service: CustomerSessionService,
) -> None:
    session_service.initialize()

    assert session_service.catalog.profile_ids == ("small-business", "startup")
    assert tuple(value.value for value in session_service.catalog.business_borrower_types) == (
        "SOLE_PROPRIETOR",
        "CORPORATION",
    )


def test_create_demo_session_by_business_borrower_type(client: TestClient) -> None:
    sole_proprietor = client.post(
        "/v1/sessions/demo",
        json={"businessBorrowerType": "SOLE_PROPRIETOR"},
    )
    corporation = client.post(
        "/v1/sessions/demo",
        json={"businessBorrowerType": "CORPORATION"},
    )

    assert sole_proprietor.status_code == 201
    assert corporation.status_code == 201
    assert (
        sole_proprietor.json()["session"]["demoProfile"]["businessBorrowerType"]
        == "SOLE_PROPRIETOR"
    )
    assert (
        sole_proprietor.json()["session"]["customerSubject"]["primaryBusiness"]["legalForm"]
        == "SOLE_PROPRIETOR"
    )
    assert corporation.json()["session"]["demoProfile"]["businessBorrowerType"] == "CORPORATION"
    assert (
        corporation.json()["session"]["customerSubject"]["primaryBusiness"]["legalForm"]
        == "CORPORATION"
    )


def test_demo_session_requires_exactly_one_selector(client: TestClient) -> None:
    missing = client.post("/v1/sessions/demo", json={})
    duplicate = client.post(
        "/v1/sessions/demo",
        json={
            "demoProfileId": "small-business",
            "businessBorrowerType": "SOLE_PROPRIETOR",
        },
    )
    personal_loan = client.post(
        "/v1/sessions/demo",
        json={"businessBorrowerType": "INDIVIDUAL"},
    )

    assert missing.status_code == 422
    assert duplicate.status_code == 422
    assert personal_loan.status_code == 422


def test_unknown_demo_profile_uses_standard_error_contract(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "unknown"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "DEMO_PROFILE_NOT_FOUND"
    assert body["error"]["requestId"].startswith("req_")
    assert body["error"]["retryable"] is False


def test_unknown_session_uses_standard_error_contract(client: TestClient) -> None:
    response = client.get("/v1/sessions/ses_does_not_exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "CUSTOMER_SESSION_NOT_FOUND"
    assert body["error"]["requestId"].startswith("req_")
    assert body["error"]["retryable"] is False
