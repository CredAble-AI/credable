from fastapi.testclient import TestClient

from app.repositories.case_repository import SqliteCaseRepository
from app.schemas.audit import AuditStage
from app.services.case_service import CaseService


def test_create_and_restore_demo_case(
    client: TestClient,
    case_repository: SqliteCaseRepository,
) -> None:
    create_response = client.post(
        "/v1/cases/demo",
        json={"demoCaseId": "borderline"},
    )

    assert create_response.status_code == 200
    assert create_response.headers["X-Request-ID"].startswith("req_")
    created = create_response.json()
    assert created["caseId"] == "case-demo-borderline"
    assert created["case"]["application"]["industry"] == "FOOD_SERVICE"
    assert created["case"]["declineReasonCodes"] == [
        "FINANCIAL_HISTORY_THIN",
        "RECENT_PERFORMANCE_NOT_REFLECTED",
    ]
    assert created["case"]["demoOnly"] is True

    get_response = client.get("/v1/cases/case-demo-borderline")

    assert get_response.status_code == 200
    assert get_response.json() == {"case": created["case"]}

    reopened_repository = SqliteCaseRepository(case_repository.database_path)
    reopened_repository.initialize()
    stored = reopened_repository.get_case("case-demo-borderline")
    original = case_repository.get_case("case-demo-borderline")
    assert stored is not None
    assert original is not None
    assert stored.case == original.case


def test_demo_case_creation_is_idempotent(
    client: TestClient,
    case_repository: SqliteCaseRepository,
) -> None:
    first = client.post("/v1/cases/demo", json={"demoCaseId": "hard-decline"})
    second = client.post("/v1/cases/demo", json={"demoCaseId": "hard-decline"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()

    events = case_repository.list_audit_events("case-demo-hard-decline")
    assert len(events) == 1
    assert events[0].stage == AuditStage.CASE_CREATED
    assert events[0].input_version == "demo-cases-v1"
    assert len(events[0].input_snapshot_hash) == 64


def test_catalog_contains_four_deterministic_demo_cases(case_service: CaseService) -> None:
    case_service.initialize()

    assert case_service.catalog.case_ids == (
        "hard-decline",
        "borderline",
        "no-data",
        "suspicious",
    )


def test_unknown_demo_case_uses_standard_error_contract(client: TestClient) -> None:
    response = client.post("/v1/cases/demo", json={"demoCaseId": "unknown"})

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "DEMO_CASE_NOT_FOUND"
    assert body["error"]["requestId"].startswith("req_")
    assert body["error"]["retryable"] is False


def test_unknown_case_uses_standard_error_contract(client: TestClient) -> None:
    response = client.get("/v1/cases/case-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "CASE_NOT_FOUND"
    assert body["error"]["requestId"].startswith("req_")
    assert body["error"]["retryable"] is False
