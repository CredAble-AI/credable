from datetime import date

from fastapi.testclient import TestClient

from app.adapters.product_catalog_adapter import ProductCatalogAdapter
from app.adapters.product_condition_adapter import ProductConditionAdapter
from app.schemas.product import (
    AnnualRateRange,
    BankProduct,
    MoneyAmount,
    ProductCatalogAdapterResult,
    ProductCatalogStatus,
    ProductOfficialSource,
    TermRangeMonths,
)
from app.schemas.product_condition import (
    ProductConditionAdapterInput,
    ProductConditionAdapterResult,
    ProductConditionStatus,
)
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService


def create_session(client: TestClient) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": "startup"},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def product(product_id: str, version: str = "v1") -> BankProduct:
    return BankProduct(
        product_id=product_id,
        product_name=f"계약 검증용 합성 상품 {product_id} {version}",
        eligibility_summary="테스트 계약 검증용 합성 가입대상",
        public_max_amount=MoneyAmount(amount="10000000", currency="KRW"),
        annual_rate_range=AnnualRateRange(
            min_percent="4.50",
            max_percent="8.00",
        ),
        term_range_months=TermRangeMonths(min_months=12, max_months=60),
        repayment_methods=["계약 검증용 방식"],
        official_source=ProductOfficialSource(
            source_name="계약 테스트 Fixture",
            effective_date=date(2026, 9, 1),
        ),
        product_version=f"contract-test-product-{version}",
    )


class AvailableCatalogAdapter(ProductCatalogAdapter):
    def __init__(self, version: str = "v1") -> None:
        self.version = version

    @property
    def adapter_version(self) -> str:
        return f"contract-test-catalog-adapter-{self.version}"

    def load(self) -> ProductCatalogAdapterResult:
        return ProductCatalogAdapterResult(
            status=ProductCatalogStatus.AVAILABLE,
            products=[product("product-b", self.version), product("product-a", self.version)],
            catalog_version=f"contract-test-catalog-{self.version}",
        )

    def is_ready(self) -> bool:
        return True


class PersonalizedConditionAdapter(ProductConditionAdapter):
    def __init__(self, fail_product_id: str | None = None) -> None:
        self.fail_product_id = fail_product_id

    def query(
        self,
        input_data: ProductConditionAdapterInput,
    ) -> ProductConditionAdapterResult:
        if input_data.product.product_id == self.fail_product_id:
            raise RuntimeError("private condition failure")
        return ProductConditionAdapterResult(
            status=ProductConditionStatus.PERSONALIZED_AVAILABLE,
            personalized_max_amount=MoneyAmount(amount="7000000", currency="KRW"),
            personalized_annual_rate_range=AnnualRateRange(
                min_percent="5.00",
                max_percent="6.50",
            ),
            personalized_term_range_months=TermRangeMonths(
                min_months=12,
                max_months=36,
            ),
            policy_version="contract-test-policy-v1",
        )

    def is_ready(self) -> bool:
        return True


def load_catalog(
    client: TestClient,
    session_id: str,
    catalog_service: ProductCatalogService,
    version: str = "v1",
) -> None:
    catalog_service.adapter = AvailableCatalogAdapter(version)
    response = client.post(f"/v1/sessions/{session_id}/products/refresh")
    assert response.status_code == 200
    assert response.json()["catalog"]["status"] == "AVAILABLE"


def test_comparison_reports_unavailable_catalog(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/comparison")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CATALOG_UNAVAILABLE"
    assert body["items"] == []
    assert body["reasonCode"] == "PRODUCT_CATALOG_NOT_LOADED"
    assert body["sortableFields"] == []
    assert body["nullPlacement"] == "LAST"
    assert body["initialOrder"] == "CATALOG_SOURCE"
    assert body["demoOnly"] is True


def test_public_catalog_keeps_source_order_and_exposes_only_available_sorts(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
) -> None:
    session_id = create_session(client)
    load_catalog(client, session_id, product_catalog_service)

    response = client.get(f"/v1/sessions/{session_id}/comparison")

    body = response.json()
    assert body["status"] == "PUBLIC_ONLY"
    assert body["reasonCode"] == "PRODUCT_CONDITIONS_NOT_QUERIED"
    assert [item["productId"] for item in body["items"]] == [
        "product-b",
        "product-a",
    ]
    assert body["sortableFields"] == [
        "PUBLIC_MAX_AMOUNT",
        "PUBLIC_MIN_ANNUAL_RATE",
    ]
    for item in body["items"]:
        assert item["personalizedConditions"] is None
        assert item["conditionStatus"] is None
        assert item["finalApprovalRequired"] is True


def test_policy_not_configured_remains_public_only_with_item_status(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
) -> None:
    session_id = create_session(client)
    load_catalog(client, session_id, product_catalog_service)
    query_response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    response = client.get(f"/v1/sessions/{session_id}/comparison")

    body = response.json()
    assert body["status"] == "PUBLIC_ONLY"
    assert body["conditionQueryId"] == query_response.json()["query"]["queryId"]
    assert body["reasonCode"] is None
    assert {item["conditionStatus"] for item in body["items"]} == {"POLICY_NOT_CONFIGURED"}
    assert all(item["personalizedConditions"] is None for item in body["items"])


def test_partial_personalization_keeps_public_and_personalized_values_separate(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    session_id = create_session(client)
    load_catalog(client, session_id, product_catalog_service)
    product_condition_service.adapter = PersonalizedConditionAdapter("product-a")
    client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    response = client.get(f"/v1/sessions/{session_id}/comparison")

    body = response.json()
    assert body["status"] == "PARTIAL"
    items = {item["productId"]: item for item in body["items"]}
    assert items["product-b"]["publicConditions"]["maxAmount"]["amount"] == "10000000"
    assert items["product-b"]["personalizedConditions"]["maxAmount"]["amount"] == "7000000"
    assert items["product-a"]["conditionStatus"] == "QUERY_FAILED"
    assert items["product-a"]["personalizedConditions"] is None
    assert body["sortableFields"] == [
        "PUBLIC_MAX_AMOUNT",
        "PUBLIC_MIN_ANNUAL_RATE",
        "PERSONALIZED_MAX_AMOUNT",
        "PERSONALIZED_MIN_ANNUAL_RATE",
    ]
    assert "recommend" not in response.text.lower()
    assert "rank" not in response.text.lower()
    assert "best" not in response.text.lower()


def test_all_personalized_conditions_make_comparison_available(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    session_id = create_session(client)
    load_catalog(client, session_id, product_catalog_service)
    product_condition_service.adapter = PersonalizedConditionAdapter()
    client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    response = client.get(f"/v1/sessions/{session_id}/comparison")

    assert response.json()["status"] == "AVAILABLE"
    assert all(item["personalizedConditions"] is not None for item in response.json()["items"])


def test_conditions_from_previous_catalog_are_not_connected(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
) -> None:
    session_id = create_session(client)
    load_catalog(client, session_id, product_catalog_service, "v1")
    client.post(f"/v1/sessions/{session_id}/product-conditions/query")
    load_catalog(client, session_id, product_catalog_service, "v2")

    response = client.get(f"/v1/sessions/{session_id}/comparison")

    body = response.json()
    assert body["status"] == "PUBLIC_ONLY"
    assert body["conditionQueryId"] is None
    assert body["reasonCode"] == "PRODUCT_CONDITIONS_OUTDATED"
    assert all(item["conditionStatus"] is None for item in body["items"])


def test_unknown_session_uses_standard_error(client: TestClient) -> None:
    response = client.get("/v1/sessions/ses_missing/comparison")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_SESSION_NOT_FOUND"
    assert response.json()["error"]["requestId"].startswith("req_")
