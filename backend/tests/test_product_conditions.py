from datetime import date

from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import AssessmentAdapter
from app.adapters.product_catalog_adapter import DemoProductCatalogAdapter, ProductCatalogAdapter
from app.adapters.product_condition_adapter import (
    DemoProductConditionAdapter,
    ProductConditionAdapter,
)
from app.core.config import settings
from app.repositories.product_condition_repository import SqliteProductConditionRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.assessment import (
    AdapterAssessmentResult,
    AssessmentInputSnapshot,
    AssessmentStatus,
    AssessmentUncertainty,
    CalibrationMode,
)
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
from app.schemas.product_condition import (
    ProductConditionAdapterInput,
    ProductConditionAdapterResult,
    ProductConditionStatus,
)
from app.services.assessment_service import AssessmentService
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService


def create_session(client: TestClient, demo_profile_id: str = "small-business") -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def product(product_id: str) -> BankProduct:
    return BankProduct(
        product_id=product_id,
        product_name=f"계약 검증용 합성 상품 {product_id}",
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
        product_version="contract-test-product-v1",
    )


class AvailableCatalogAdapter(ProductCatalogAdapter):
    @property
    def adapter_version(self) -> str:
        return "contract-test-catalog-adapter-v1"

    def load(self) -> ProductCatalogAdapterResult:
        return ProductCatalogAdapterResult(
            status=ProductCatalogStatus.AVAILABLE,
            products=[product("product-a"), product("product-b")],
            catalog_version="contract-test-catalog-v1",
        )

    def is_ready(self) -> bool:
        return True


class MixedConditionAdapter(ProductConditionAdapter):
    def query(
        self,
        input_data: ProductConditionAdapterInput,
    ) -> ProductConditionAdapterResult:
        if input_data.product.product_id == "product-b":
            raise RuntimeError("private policy detail must not escape")
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


class FailingConditionAdapter(ProductConditionAdapter):
    def query(
        self,
        input_data: ProductConditionAdapterInput,
    ) -> ProductConditionAdapterResult:
        del input_data
        raise RuntimeError("private policy detail must not escape")

    def is_ready(self) -> bool:
        return True


class CompletedAssessmentAdapter(AssessmentAdapter):
    def run(self, snapshot: AssessmentInputSnapshot) -> AdapterAssessmentResult:
        del snapshot
        return AdapterAssessmentResult(
            status=AssessmentStatus.COMPLETED,
            model_version="contract-test-assessment-v1",
            uncertainty=AssessmentUncertainty(
                grade_set=["TEST_GRADE_B", "TEST_GRADE_C"],
                calibration_mode=CalibrationMode.RULE_TABLE,
                calibration_version="contract-test-rule-v1",
            ),
        )

    def is_ready(self) -> bool:
        return True


def load_catalog(
    client: TestClient,
    session_id: str,
    product_catalog_service: ProductCatalogService,
) -> None:
    product_catalog_service.adapter = AvailableCatalogAdapter()
    response = client.post(f"/v1/sessions/{session_id}/products/refresh")
    assert response.status_code == 200
    assert response.json()["catalog"]["status"] == "AVAILABLE"


def test_conditions_are_not_queried_before_first_execution(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/sessions/{session_id}/product-conditions")

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": session_id,
        "query": {
            "queryId": None,
            "status": "NOT_QUERIED",
            "conditions": [],
            "queriedAt": None,
            "catalogSnapshotId": None,
            "assessmentId": None,
            "dataSnapshotId": None,
            "reasonCode": None,
            "demoOnly": True,
        },
    }


def test_query_without_catalog_returns_explicit_unavailable_state(
    client: TestClient,
    product_condition_repository: SqliteProductConditionRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)

    response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    assert response.status_code == 200
    query = response.json()["query"]
    assert query["queryId"].startswith("pcq_")
    assert query["status"] == "CATALOG_UNAVAILABLE"
    assert query["conditions"] == []
    assert query["reasonCode"] == "PRODUCT_CATALOG_NOT_LOADED"
    assert query["demoOnly"] is True
    assert product_condition_repository.count_queries(session_id) == 1

    event = session_repository.list_audit_events(session_id)[-1]
    assert event.stage == AuditStage.PRODUCT_CONDITIONS_QUERIED
    assert event.output_summary == {
        "queryStatus": "CATALOG_UNAVAILABLE",
        "productCount": 0,
        "failedCount": 0,
        "demoOnly": True,
    }


def test_products_without_policy_return_policy_not_configured(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
    product_condition_repository: SqliteProductConditionRepository,
) -> None:
    session_id = create_session(client)
    load_catalog(client, session_id, product_catalog_service)

    response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    assert response.status_code == 200
    query = response.json()["query"]
    assert query["status"] == "COMPLETED"
    assert len(query["conditions"]) == 2
    for condition in query["conditions"]:
        assert condition["status"] == "POLICY_NOT_CONFIGURED"
        assert condition["personalizedMaxAmount"] is None
        assert condition["personalizedAnnualRateRange"] is None
        assert condition["personalizedTermRangeMonths"] is None
        assert condition["policyVersion"] is None
        assert condition["reasonCode"] == "DEMO_PRODUCT_POLICY_NOT_CONFIGURED"
        assert condition["finalApprovalRequired"] is True

    snapshot = product_condition_repository.get_snapshot(query["queryId"])
    assert snapshot is not None
    assert [item.product_id for item in snapshot.products] == [
        "product-a",
        "product-b",
    ]
    assert snapshot.catalog_snapshot_id == query["catalogSnapshotId"]
    assert snapshot.data_snapshot_id == query["dataSnapshotId"]


def test_demo_policy_matches_frontend_fixture_for_small_business(
    client: TestClient,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    session_id = create_session(client)
    product_catalog_service.adapter = DemoProductCatalogAdapter(settings.demo_products_path)
    product_condition_service.adapter = DemoProductConditionAdapter(
        settings.demo_product_conditions_path
    )
    assessment_service.adapter = CompletedAssessmentAdapter()
    client.post(f"/v1/sessions/{session_id}/assessment/run")
    client.post(f"/v1/sessions/{session_id}/products/refresh")

    response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    assert response.status_code == 200
    query = response.json()["query"]
    assert query["status"] == "PARTIAL"
    conditions = {item["productId"]: item for item in query["conditions"]}
    assert conditions["demo-working-capital"] == {
        "productId": "demo-working-capital",
        "status": "PERSONALIZED_AVAILABLE",
        "personalizedMaxAmount": {"amount": "24000000", "currency": "KRW"},
        "personalizedAnnualRateRange": {
            "minPercent": "5.10",
            "maxPercent": "7.30",
        },
        "personalizedTermRangeMonths": {"minMonths": 12, "maxMonths": 48},
        "policyVersion": "demo-policy-v1",
        "queriedAt": query["queriedAt"],
        "reasonCode": None,
        "finalApprovalRequired": True,
        "demoOnly": True,
    }
    assert conditions["demo-daily-bridge"]["status"] == "PUBLIC_ONLY"
    assert conditions["demo-steady-business"]["status"] == "INSUFFICIENT_DATA"
    assert conditions["demo-steady-business"]["reasonCode"] == "DEMO_PRODUCT_DATA_INSUFFICIENT"
    assert conditions["demo-balance-partner"]["status"] == "QUERY_FAILED"
    assert conditions["demo-balance-partner"]["reasonCode"] == "DEMO_PRODUCT_CONDITION_UNAVAILABLE"

    comparison = client.get(f"/v1/sessions/{session_id}/comparison").json()
    assert comparison["status"] == "PARTIAL"
    assert comparison["sortableFields"] == [
        "PUBLIC_MAX_AMOUNT",
        "PUBLIC_MIN_ANNUAL_RATE",
        "PERSONALIZED_MAX_AMOUNT",
        "PERSONALIZED_MIN_ANNUAL_RATE",
    ]


def test_demo_policy_requires_completed_assessment(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    session_id = create_session(client)
    product_catalog_service.adapter = DemoProductCatalogAdapter(settings.demo_products_path)
    product_condition_service.adapter = DemoProductConditionAdapter(
        settings.demo_product_conditions_path
    )
    client.post(f"/v1/sessions/{session_id}/products/refresh")

    response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    query = response.json()["query"]
    assert query["status"] == "COMPLETED"
    assert {item["status"] for item in query["conditions"]} == {"INSUFFICIENT_DATA"}
    assert {item["reasonCode"] for item in query["conditions"]} == {"DEMO_ASSESSMENT_NOT_COMPLETED"}
    assert all(item["personalizedMaxAmount"] is None for item in query["conditions"])


def test_demo_policy_does_not_invent_startup_conditions(
    client: TestClient,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
    product_condition_repository: SqliteProductConditionRepository,
) -> None:
    session_id = create_session(client, "startup")
    product_catalog_service.adapter = DemoProductCatalogAdapter(settings.demo_products_path)
    product_condition_service.adapter = DemoProductConditionAdapter(
        settings.demo_product_conditions_path
    )
    assessment_service.adapter = CompletedAssessmentAdapter()
    client.post(f"/v1/sessions/{session_id}/assessment/run")
    client.post(f"/v1/sessions/{session_id}/products/refresh")

    response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    query = response.json()["query"]
    assert query["status"] == "COMPLETED"
    assert {item["status"] for item in query["conditions"]} == {"POLICY_NOT_CONFIGURED"}
    assert all(item["policyVersion"] is None for item in query["conditions"])
    assert all(item["personalizedMaxAmount"] is None for item in query["conditions"])
    snapshot = product_condition_repository.get_snapshot(query["queryId"])
    assert snapshot is not None
    assert snapshot.demo_profile_id == "startup"

    comparison = client.get(f"/v1/sessions/{session_id}/comparison").json()
    assert comparison["status"] == "PUBLIC_ONLY"
    assert all(item["personalizedConditions"] is None for item in comparison["items"])


def test_partial_failure_keeps_other_product_condition(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    session_id = create_session(client)
    load_catalog(client, session_id, product_catalog_service)
    product_condition_service.adapter = MixedConditionAdapter()

    response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    assert response.status_code == 200
    query = response.json()["query"]
    assert query["status"] == "PARTIAL"
    conditions = {item["productId"]: item for item in query["conditions"]}
    assert conditions["product-a"]["status"] == "PERSONALIZED_AVAILABLE"
    assert conditions["product-a"]["personalizedMaxAmount"] == {
        "amount": "7000000",
        "currency": "KRW",
    }
    assert conditions["product-a"]["policyVersion"] == "contract-test-policy-v1"
    assert conditions["product-b"]["status"] == "QUERY_FAILED"
    assert conditions["product-b"]["reasonCode"] == "PRODUCT_CONDITION_ADAPTER_ERROR"
    assert "private policy detail" not in response.text
    assert "recommend" not in response.text.lower()
    assert "best" not in response.text.lower()


def test_all_product_failures_set_batch_failed(
    client: TestClient,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    session_id = create_session(client)
    load_catalog(client, session_id, product_catalog_service)
    product_condition_service.adapter = FailingConditionAdapter()

    response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")

    query = response.json()["query"]
    assert query["status"] == "FAILED"
    assert query["reasonCode"] == "ALL_PRODUCT_QUERIES_FAILED"
    assert {item["status"] for item in query["conditions"]} == {"QUERY_FAILED"}


def test_each_query_is_preserved_and_get_returns_latest(
    client: TestClient,
    product_condition_repository: SqliteProductConditionRepository,
) -> None:
    session_id = create_session(client)

    first = client.post(f"/v1/sessions/{session_id}/product-conditions/query").json()
    second = client.post(f"/v1/sessions/{session_id}/product-conditions/query").json()
    latest = client.get(f"/v1/sessions/{session_id}/product-conditions").json()

    assert first["query"]["queryId"] != second["query"]["queryId"]
    assert product_condition_repository.count_queries(session_id) == 2
    assert latest == second


def test_unknown_session_uses_standard_error(client: TestClient) -> None:
    response = client.post("/v1/sessions/ses_missing/product-conditions/query")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_SESSION_NOT_FOUND"
    assert response.json()["error"]["requestId"].startswith("req_")
