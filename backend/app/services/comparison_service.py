from datetime import UTC, datetime

from app.schemas.comparison import (
    ComparisonSortField,
    ComparisonStatus,
    PersonalizedProductConditions,
    ProductComparisonItem,
    ProductComparisonResponse,
    PublicProductConditions,
)
from app.schemas.product import BankProduct, ProductCatalogStatus
from app.schemas.product_condition import (
    ProductCondition,
    ProductConditionQueryStatus,
    ProductConditionStatus,
)
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService
from app.services.session_service import CustomerSessionService


class ProductComparisonService:
    def __init__(
        self,
        session_service: CustomerSessionService,
        catalog_service: ProductCatalogService,
        condition_service: ProductConditionService,
    ) -> None:
        self.session_service = session_service
        self.catalog_service = catalog_service
        self.condition_service = condition_service

    def get_comparison(self, session_id: str) -> ProductComparisonResponse:
        self.session_service.get_session(session_id)
        assembled_at = datetime.now(UTC)
        catalog = self.catalog_service.get_latest(session_id).catalog
        if catalog.status != ProductCatalogStatus.AVAILABLE:
            return ProductComparisonResponse(
                session_id=session_id,
                status=ComparisonStatus.CATALOG_UNAVAILABLE,
                items=[],
                assembled_at=assembled_at,
                catalog_snapshot_id=catalog.catalog_snapshot_id,
                reason_code=catalog.reason_code or f"PRODUCT_CATALOG_{catalog.status.value}",
                sortable_fields=[],
            )

        query = self.condition_service.get_latest(session_id).query
        query_is_current = (
            query.status
            not in {
                ProductConditionQueryStatus.NOT_QUERIED,
                ProductConditionQueryStatus.CATALOG_UNAVAILABLE,
            }
            and query.catalog_snapshot_id == catalog.catalog_snapshot_id
        )
        conditions = (
            {item.product_id: item for item in query.conditions} if query_is_current else {}
        )
        items = [
            self._item(product, conditions.get(product.product_id)) for product in catalog.products
        ]
        status = self._status(items)
        reason_code = None
        condition_query_id = None
        if not query_is_current:
            reason_code = (
                "PRODUCT_CONDITIONS_NOT_QUERIED"
                if query.status == ProductConditionQueryStatus.NOT_QUERIED
                else "PRODUCT_CONDITIONS_OUTDATED"
            )
        else:
            condition_query_id = query.query_id
            if status == ComparisonStatus.PARTIAL:
                reason_code = query.reason_code or "PERSONALIZED_CONDITIONS_PARTIAL"
        return ProductComparisonResponse(
            session_id=session_id,
            status=status,
            items=items,
            assembled_at=assembled_at,
            catalog_snapshot_id=catalog.catalog_snapshot_id,
            condition_query_id=condition_query_id,
            reason_code=reason_code,
            sortable_fields=self._sortable_fields(items),
        )

    def _item(
        self,
        product: BankProduct,
        condition: ProductCondition | None,
    ) -> ProductComparisonItem:
        personalized = None
        if (
            condition is not None
            and condition.status == ProductConditionStatus.PERSONALIZED_AVAILABLE
            and condition.policy_version is not None
        ):
            personalized = PersonalizedProductConditions(
                max_amount=condition.personalized_max_amount,
                annual_rate_range=condition.personalized_annual_rate_range,
                term_range_months=condition.personalized_term_range_months,
                policy_version=condition.policy_version,
                queried_at=condition.queried_at,
            )
        return ProductComparisonItem(
            product_id=product.product_id,
            product_name=product.product_name,
            eligibility_summary=product.eligibility_summary,
            public_conditions=PublicProductConditions(
                max_amount=product.public_max_amount,
                annual_rate_range=product.annual_rate_range,
                term_range_months=product.term_range_months,
                repayment_methods=product.repayment_methods,
            ),
            personalized_conditions=personalized,
            condition_status=condition.status if condition else None,
            condition_reason_code=condition.reason_code if condition else None,
            official_source=product.official_source,
            product_version=product.product_version,
            application_url=product.application_url,
            application_reference=product.application_reference,
        )

    def _status(self, items: list[ProductComparisonItem]) -> ComparisonStatus:
        personalized_count = sum(item.personalized_conditions is not None for item in items)
        failure_exists = any(
            item.condition_status == ProductConditionStatus.QUERY_FAILED for item in items
        )
        if items and personalized_count == len(items):
            return ComparisonStatus.AVAILABLE
        if personalized_count or failure_exists:
            return ComparisonStatus.PARTIAL
        return ComparisonStatus.PUBLIC_ONLY

    def _sortable_fields(
        self,
        items: list[ProductComparisonItem],
    ) -> list[ComparisonSortField]:
        fields: list[ComparisonSortField] = []
        if any(item.public_conditions.max_amount is not None for item in items):
            fields.append(ComparisonSortField.PUBLIC_MAX_AMOUNT)
        if any(item.public_conditions.annual_rate_range is not None for item in items):
            fields.append(ComparisonSortField.PUBLIC_MIN_ANNUAL_RATE)
        if any(
            item.personalized_conditions is not None
            and item.personalized_conditions.max_amount is not None
            for item in items
        ):
            fields.append(ComparisonSortField.PERSONALIZED_MAX_AMOUNT)
        if any(
            item.personalized_conditions is not None
            and item.personalized_conditions.annual_rate_range is not None
            for item in items
        ):
            fields.append(ComparisonSortField.PERSONALIZED_MIN_ANNUAL_RATE)
        return fields
