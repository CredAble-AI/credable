from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import DemoAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.adapters.product_catalog_adapter import DemoProductCatalogAdapter
from app.adapters.product_condition_adapter import DemoProductConditionAdapter
from app.core.config import settings
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService


def configure_demo_adapters(
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    product_catalog_service.adapter = DemoProductCatalogAdapter(settings.demo_products_path)
    product_condition_service.adapter = DemoProductConditionAdapter(
        settings.demo_product_conditions_path
    )


def create_session(client: TestClient, demo_profile_id: str) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def grant_sources(
    client: TestClient,
    session_id: str,
    source_types: tuple[ConsentSourceType, ...],
) -> None:
    for source_type in source_types:
        response = client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant")
        assert response.status_code == 200


def test_small_business_demo_flow_reaches_partial_comparison(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    configure_demo_adapters(
        data_source_service,
        assessment_service,
        product_catalog_service,
        product_condition_service,
    )
    session_id = create_session(client, "small-business")
    grant_sources(
        client,
        session_id,
        (
            ConsentSourceType.BANK_INTERNAL,
            ConsentSourceType.CREDIT_INFORMATION,
        ),
    )

    data_response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")
    assessment_response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    catalog_response = client.post(f"/v1/sessions/{session_id}/products/refresh")
    condition_response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")
    comparison_response = client.get(f"/v1/sessions/{session_id}/comparison")

    assert data_response.status_code == 200
    data_sources = {item["sourceType"]: item for item in data_response.json()["dataSources"]}
    assert data_sources["BANK_INTERNAL"]["verificationStatus"] == "VERIFIED"
    assert data_sources["CREDIT_INFORMATION"]["verificationStatus"] == "VERIFIED"
    assert data_sources["CUSTOMER_SUBMITTED"]["retrievalStatus"] == "CONSENT_REQUIRED"

    assert assessment_response.json()["assessment"]["status"] == "COMPLETED"
    assert (
        assessment_response.json()["assessment"]["modelVersion"]
        == "demo-small-business-assessment-v1"
    )
    assert catalog_response.json()["catalog"]["status"] == "AVAILABLE"
    assert len(catalog_response.json()["catalog"]["products"]) == 4
    assert condition_response.json()["query"]["status"] == "PARTIAL"

    comparison = comparison_response.json()
    assert comparison["status"] == "PARTIAL"
    assert len(comparison["items"]) == 4
    items = {item["productId"]: item for item in comparison["items"]}
    assert items["demo-working-capital"]["personalizedConditions"]["maxAmount"] == {
        "amount": "24000000",
        "currency": "KRW",
    }
    assert items["demo-daily-bridge"]["conditionStatus"] == "PUBLIC_ONLY"
    assert items["demo-steady-business"]["conditionStatus"] == "INSUFFICIENT_DATA"
    assert items["demo-balance-partner"]["conditionStatus"] == "QUERY_FAILED"
    assert "recommend" not in comparison_response.text.lower()
    assert "rank" not in comparison_response.text.lower()
    assert "best" not in comparison_response.text.lower()

    events = session_repository.list_audit_events(session_id)
    assert [event.stage for event in events] == [
        AuditStage.SESSION_CREATED,
        AuditStage.CONSENT_GRANTED,
        AuditStage.CONSENT_GRANTED,
        AuditStage.DATA_SOURCE_REFRESHED,
        AuditStage.DATA_SOURCE_REFRESHED,
        AuditStage.ASSESSMENT_RUN,
        AuditStage.PRODUCT_CATALOG_REFRESHED,
        AuditStage.PRODUCT_CONDITIONS_QUERIED,
    ]
    assert events[-3].model_version == "demo-small-business-assessment-v1"
    assert events[-1].policy_version == "demo-policy-v1"
    assert all(event.output_summary["demoOnly"] is True for event in events)


def test_startup_demo_flow_keeps_unavailable_values_empty(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    configure_demo_adapters(
        data_source_service,
        assessment_service,
        product_catalog_service,
        product_condition_service,
    )
    session_id = create_session(client, "startup")
    grant_sources(client, session_id, tuple(ConsentSourceType))

    data_response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")
    assessment_response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    client.post(f"/v1/sessions/{session_id}/products/refresh")
    condition_response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")
    comparison_response = client.get(f"/v1/sessions/{session_id}/comparison")

    data_sources = {item["sourceType"]: item for item in data_response.json()["dataSources"]}
    assert data_sources["CUSTOMER_SUBMITTED"]["verificationStatus"] == "STALE"
    assert data_sources["EXTERNAL_CONNECTED"]["retrievalStatus"] == "FAILED"
    assert assessment_response.json()["assessment"]["status"] == "INSUFFICIENT_DATA"
    assert (
        assessment_response.json()["assessment"]["reasonCode"] == "DEMO_VERIFIED_DATA_INSUFFICIENT"
    )

    conditions = condition_response.json()["query"]
    assert conditions["status"] == "COMPLETED"
    assert {item["status"] for item in conditions["conditions"]} == {"INSUFFICIENT_DATA"}
    assert all(item["personalizedMaxAmount"] is None for item in conditions["conditions"])

    comparison = comparison_response.json()
    assert comparison["status"] == "PUBLIC_ONLY"
    assert len(comparison["items"]) == 4
    assert all(item["personalizedConditions"] is None for item in comparison["items"])
    assert all(item["demoOnly"] is True for item in comparison["items"])
