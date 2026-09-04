from datetime import date

from fastapi.testclient import TestClient

from app.adapters.product_catalog_adapter import (
    DemoProductCatalogAdapter,
    ProductCatalogAdapter,
)
from app.core.config import settings
from app.repositories.product_catalog_repository import SqliteProductCatalogRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.product import (
    AnnualRateRange,
    BankProduct,
    MoneyAmount,
    ProductCatalogAdapterResult,
    ProductCatalogStatus,
    ProductOfficialSource,
    TermRangeMonths,
)
from app.services.product_catalog_service import ProductCatalogService


def create_session(client: TestClient) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "small-business"},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


class AvailableCatalogAdapter(ProductCatalogAdapter):
    @property
    def adapter_version(self) -> str:
        return "contract-test-adapter-v1"

    def load(self) -> ProductCatalogAdapterResult:
        return ProductCatalogAdapterResult(
            status=ProductCatalogStatus.AVAILABLE,
            catalog_version="contract-test-catalog-v1",
            products=[
                BankProduct(
                    product_id="product-contract-test",
                    product_name="계약 검증용 합성 상품",
                    eligibility_summary="테스트 계약 검증용 합성 가입대상",
                    public_max_amount=MoneyAmount(amount="10000000", currency="KRW"),
                    annual_rate_range=AnnualRateRange(
                        min_percent="4.50",
                        max_percent="8.00",
                    ),
                    term_range_months=TermRangeMonths(
                        min_months=12,
                        max_months=60,
                    ),
                    repayment_methods=["계약 검증용 방식"],
                    official_source=ProductOfficialSource(
                        source_name="계약 테스트 Fixture",
                        source_url="https://example.test/products/contract-test",
                        effective_date=date(2026, 9, 1),
                    ),
                    product_version="contract-test-product-v1",
                    application_reference="contract-test-application",
                )
            ],
        )

    def is_ready(self) -> bool:
        return True


class FailingCatalogAdapter(ProductCatalogAdapter):
    @property
    def adapter_version(self) -> str:
        return "failing-contract-test-adapter-v1"

    def load(self) -> ProductCatalogAdapterResult:
        raise RuntimeError("private bank adapter detail must not escape")

    def is_ready(self) -> bool:
        return True


def test_catalog_is_not_loaded_before_first_refresh(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/products")

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": session_id,
        "catalog": {
            "status": "NOT_LOADED",
            "catalogSnapshotId": None,
            "products": [],
            "retrievedAt": None,
            "catalogVersion": None,
            "reasonCode": None,
            "demoOnly": True,
        },
    }


def test_refresh_without_product_mock_returns_not_configured_and_audit(
    client: TestClient,
    product_catalog_repository: SqliteProductCatalogRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/products/refresh")

    assert response.status_code == 200
    catalog = response.json()["catalog"]
    assert catalog["status"] == "CATALOG_NOT_CONFIGURED"
    assert catalog["catalogSnapshotId"].startswith("pcs_")
    assert catalog["products"] == []
    assert catalog["retrievedAt"].endswith("Z")
    assert catalog["catalogVersion"] is None
    assert catalog["reasonCode"] == "DEMO_PRODUCT_CATALOG_NOT_CONFIGURED"
    assert catalog["demoOnly"] is True

    reopened = SqliteProductCatalogRepository(product_catalog_repository.database_path)
    reopened.initialize()
    stored = reopened.get_latest(session_id)
    assert stored is not None
    assert stored.model_dump(mode="json", by_alias=True) == catalog

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.PRODUCT_CATALOG_REFRESHED
    assert event.request_id == response.headers["X-Request-ID"]
    assert event.output_summary == {
        "catalogStatus": "CATALOG_NOT_CONFIGURED",
        "productCount": 0,
        "demoOnly": True,
    }


def test_demo_catalog_matches_frontend_fixture_and_is_comparison_ready(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
) -> None:
    session_id = create_session(client)
    adapter = DemoProductCatalogAdapter(settings.demo_products_path)
    product_catalog_service.adapter = adapter

    response = client.post(f"/v1/sessions/{session_id}/products/refresh")

    assert adapter.is_ready() is True
    assert response.status_code == 200
    catalog = response.json()["catalog"]
    assert catalog["status"] == "AVAILABLE"
    assert catalog["catalogVersion"] == "demo-catalog-v1"
    assert [item["productId"] for item in catalog["products"]] == [
        "demo-working-capital",
        "demo-daily-bridge",
        "demo-steady-business",
        "demo-balance-partner",
    ]
    assert [item["publicMaxAmount"]["amount"] for item in catalog["products"]] == [
        "50000000",
        "30000000",
        "70000000",
        "40000000",
    ]
    assert all(item["demoOnly"] is True for item in catalog["products"])
    assert all("합성" in item["eligibilitySummary"] for item in catalog["products"])

    comparison = client.get(f"/v1/sessions/{session_id}/comparison").json()
    assert comparison["status"] == "PUBLIC_ONLY"
    assert len(comparison["items"]) == 4
    assert [item["productId"] for item in comparison["items"]] == [
        "demo-working-capital",
        "demo-daily-bridge",
        "demo-steady-business",
        "demo-balance-partner",
    ]


def test_available_catalog_keeps_public_conditions_structured(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
) -> None:
    session_id = create_session(client)
    product_catalog_service.adapter = AvailableCatalogAdapter()

    response = client.post(f"/v1/sessions/{session_id}/products/refresh")

    assert response.status_code == 200
    catalog = response.json()["catalog"]
    assert catalog["status"] == "AVAILABLE"
    assert catalog["catalogVersion"] == "contract-test-catalog-v1"
    product = catalog["products"][0]
    assert product["publicMaxAmount"] == {
        "amount": "10000000",
        "currency": "KRW",
    }
    assert product["annualRateRange"] == {
        "minPercent": "4.50",
        "maxPercent": "8.00",
    }
    assert product["termRangeMonths"] == {"minMonths": 12, "maxMonths": 60}
    assert product["officialSource"]["effectiveDate"] == "2026-09-01"
    assert "personalized" not in response.text.lower()
    assert "recommend" not in response.text.lower()


def test_each_refresh_is_preserved_and_get_returns_latest(
    client: TestClient,
    product_catalog_repository: SqliteProductCatalogRepository,
) -> None:
    session_id = create_session(client)

    first = client.post(f"/v1/sessions/{session_id}/products/refresh").json()
    second = client.post(f"/v1/sessions/{session_id}/products/refresh").json()
    latest = client.get(f"/v1/sessions/{session_id}/products").json()

    assert first["catalog"]["catalogSnapshotId"] == second["catalog"]["catalogSnapshotId"]
    assert product_catalog_repository.count_snapshots(session_id) == 2
    assert latest == second


def test_adapter_failure_is_sanitized(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
) -> None:
    session_id = create_session(client)
    product_catalog_service.adapter = FailingCatalogAdapter()

    response = client.post(f"/v1/sessions/{session_id}/products/refresh")

    assert response.status_code == 200
    catalog = response.json()["catalog"]
    assert catalog["status"] == "FAILED"
    assert catalog["reasonCode"] == "PRODUCT_CATALOG_ADAPTER_ERROR"
    assert catalog["products"] == []
    assert "private bank adapter detail" not in response.text


def test_unknown_session_uses_standard_error(client: TestClient) -> None:
    response = client.get("/v1/sessions/ses_missing/products")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_SESSION_NOT_FOUND"
    assert response.json()["error"]["requestId"].startswith("req_")
