from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.adapters.data_source_adapter import DataSourceAdapter, DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.data_source_repository import SqliteDataSourceRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.schemas.data_source import (
    AdapterRetrievalResult,
    RetrievalStatus,
    VerificationStatus,
)
from app.services.data_source_service import DataSourceService


def create_session(client: TestClient, demo_profile_id: str = "small-business") -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def grant(client: TestClient, session_id: str, source_type: str) -> None:
    response = client.post(f"/v1/sessions/{session_id}/consents/{source_type}/grant")
    assert response.status_code == 200


class ResultAdapter(DataSourceAdapter):
    def retrieve(
        self,
        *,
        session_id: str,
        demo_profile_id: str,
        source_type: ConsentSourceType,
    ) -> AdapterRetrievalResult:
        del session_id, demo_profile_id
        if source_type == ConsentSourceType.CREDIT_INFORMATION:
            raise RuntimeError("sensitive adapter detail must not escape")
        return AdapterRetrievalResult(
            retrieval_status=RetrievalStatus.RETRIEVED,
            verification_status=VerificationStatus.VERIFIED,
            observed_at=datetime(2026, 9, 1, tzinfo=UTC),
            data_version="mock-source-v1",
        )

    def is_ready(self) -> bool:
        return True


def test_ungranted_sources_require_consent(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/data-sources")

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == session_id
    assert body["demoOnly"] is True
    assert len(body["dataSources"]) == 4
    for source in body["dataSources"]:
        assert source["retrievalStatus"] == "CONSENT_REQUIRED"
        assert source["verificationStatus"] == "NOT_STARTED"
        assert source["reasonCode"] == "CONSENT_REQUIRED"
        assert source["observedAt"] is None
        assert source["retrievedAt"] is None
        assert source["dataVersion"] is None


def test_granted_source_starts_not_requested(client: TestClient) -> None:
    session_id = create_session(client)
    grant(client, session_id, "BANK_INTERNAL")

    response = client.get(f"/v1/sessions/{session_id}/data-sources")

    sources = {item["sourceType"]: item for item in response.json()["dataSources"]}
    assert sources["BANK_INTERNAL"]["retrievalStatus"] == "NOT_REQUESTED"
    assert sources["BANK_INTERNAL"]["reasonCode"] is None
    assert sources["EXTERNAL_CONNECTED"]["retrievalStatus"] == "CONSENT_REQUIRED"


def test_refresh_without_mock_data_returns_no_data_and_persists(
    client: TestClient,
    data_source_repository: SqliteDataSourceRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    grant(client, session_id, "BANK_INTERNAL")

    response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")

    assert response.status_code == 200
    sources = {item["sourceType"]: item for item in response.json()["dataSources"]}
    bank_source = sources["BANK_INTERNAL"]
    assert bank_source["retrievalStatus"] == "NO_DATA"
    assert bank_source["verificationStatus"] == "NOT_STARTED"
    assert bank_source["reasonCode"] == "DEMO_DATA_NOT_CONFIGURED"
    assert bank_source["retrievedAt"].endswith("Z")
    assert bank_source["observedAt"] is None
    assert bank_source["dataVersion"] is None

    reopened = SqliteDataSourceRepository(data_source_repository.database_path)
    reopened.initialize()
    stored = reopened.get_state(session_id, ConsentSourceType.BANK_INTERNAL)
    assert stored is not None
    assert stored.model_dump(mode="json", by_alias=True) == bank_source

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.DATA_SOURCE_REFRESHED
    assert event.data_version is None
    assert event.output_summary["retrievalStatus"] == "NO_DATA"
    assert "DEMO_DATA_NOT_CONFIGURED" not in event.input_snapshot_hash


def test_refresh_isolates_source_failure_and_records_verified_metadata(
    client: TestClient,
    data_source_service: DataSourceService,
) -> None:
    session_id = create_session(client)
    grant(client, session_id, "BANK_INTERNAL")
    grant(client, session_id, "CREDIT_INFORMATION")
    data_source_service.adapter = ResultAdapter()

    response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")

    assert response.status_code == 200
    sources = {item["sourceType"]: item for item in response.json()["dataSources"]}
    assert sources["BANK_INTERNAL"]["retrievalStatus"] == "RETRIEVED"
    assert sources["BANK_INTERNAL"]["verificationStatus"] == "VERIFIED"
    assert sources["BANK_INTERNAL"]["observedAt"] == "2026-09-01T00:00:00Z"
    assert sources["BANK_INTERNAL"]["dataVersion"] == "mock-source-v1"
    assert sources["CREDIT_INFORMATION"]["retrievalStatus"] == "FAILED"
    assert sources["CREDIT_INFORMATION"]["reasonCode"] == "DATA_SOURCE_ADAPTER_ERROR"
    assert "sensitive adapter detail" not in response.text
    assert sources["CUSTOMER_SUBMITTED"]["retrievalStatus"] == "CONSENT_REQUIRED"


def test_demo_data_sources_match_small_business_frontend_fixture(
    client: TestClient,
    data_source_service: DataSourceService,
) -> None:
    session_id = create_session(client)
    for source_type in ConsentSourceType:
        grant(client, session_id, source_type.value)
    adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    data_source_service.adapter = adapter

    response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")

    assert adapter.is_ready() is True
    assert response.status_code == 200
    sources = response.json()["dataSources"]
    assert {item["retrievalStatus"] for item in sources} == {"RETRIEVED"}
    assert {item["verificationStatus"] for item in sources} == {"VERIFIED"}
    assert {item["observedAt"] for item in sources} == {"2026-08-31T23:59:59+09:00"}
    assert {item["dataVersion"] for item in sources} == {"synthetic-demo-v1"}
    assert all(item["demoOnly"] is True for item in sources)


def test_demo_data_sources_keep_startup_stale_and_failed_states_separate(
    client: TestClient,
    data_source_service: DataSourceService,
) -> None:
    session_id = create_session(client, "startup")
    for source_type in ConsentSourceType:
        grant(client, session_id, source_type.value)
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)

    response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")

    sources = {item["sourceType"]: item for item in response.json()["dataSources"]}
    assert sources["BANK_INTERNAL"]["verificationStatus"] == "VERIFIED"
    assert sources["CREDIT_INFORMATION"]["verificationStatus"] == "VERIFIED"
    assert sources["CUSTOMER_SUBMITTED"]["retrievalStatus"] == "RETRIEVED"
    assert sources["CUSTOMER_SUBMITTED"]["verificationStatus"] == "STALE"
    assert sources["CUSTOMER_SUBMITTED"]["reasonCode"] == "DEMO_OBSERVATION_STALE"
    assert sources["EXTERNAL_CONNECTED"]["retrievalStatus"] == "FAILED"
    assert sources["EXTERNAL_CONNECTED"]["verificationStatus"] == "NOT_STARTED"
    assert sources["EXTERNAL_CONNECTED"]["reasonCode"] == "DEMO_PARTNER_UNAVAILABLE"
    assert sources["EXTERNAL_CONNECTED"]["observedAt"] is None
    assert sources["EXTERNAL_CONNECTED"]["dataVersion"] is None


def test_withdrawal_hides_stored_state_and_regrant_requires_refresh(
    client: TestClient,
    data_source_service: DataSourceService,
) -> None:
    session_id = create_session(client)
    route = f"/v1/sessions/{session_id}/consents/BANK_INTERNAL"
    grant(client, session_id, "BANK_INTERNAL")
    data_source_service.adapter = ResultAdapter()
    client.post(f"/v1/sessions/{session_id}/data-sources/refresh")

    client.post(f"{route}/withdraw")
    withdrawn = client.get(f"/v1/sessions/{session_id}/data-sources").json()
    assert withdrawn["dataSources"][0]["retrievalStatus"] == "CONSENT_REQUIRED"

    client.post(f"{route}/grant")
    regranted = client.get(f"/v1/sessions/{session_id}/data-sources").json()
    assert regranted["dataSources"][0]["retrievalStatus"] == "NOT_REQUESTED"


def test_unknown_session_uses_standard_error(client: TestClient) -> None:
    response = client.get("/v1/sessions/ses_missing/data-sources")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_SESSION_NOT_FOUND"
    assert response.json()["error"]["requestId"].startswith("req_")
