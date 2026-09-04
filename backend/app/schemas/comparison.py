from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AnyHttpUrl, Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.product import (
    AnnualRateRange,
    MoneyAmount,
    ProductOfficialSource,
    TermRangeMonths,
)
from app.schemas.product_condition import ProductConditionStatus


class ComparisonStatus(StrEnum):
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"
    PUBLIC_ONLY = "PUBLIC_ONLY"
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"


class ComparisonSortField(StrEnum):
    PUBLIC_MAX_AMOUNT = "PUBLIC_MAX_AMOUNT"
    PUBLIC_MIN_ANNUAL_RATE = "PUBLIC_MIN_ANNUAL_RATE"
    PERSONALIZED_MAX_AMOUNT = "PERSONALIZED_MAX_AMOUNT"
    PERSONALIZED_MIN_ANNUAL_RATE = "PERSONALIZED_MIN_ANNUAL_RATE"


class PublicProductConditions(ApiModel):
    max_amount: MoneyAmount | None = None
    annual_rate_range: AnnualRateRange | None = None
    term_range_months: TermRangeMonths | None = None
    repayment_methods: list[str]


class PersonalizedProductConditions(ApiModel):
    max_amount: MoneyAmount | None = None
    annual_rate_range: AnnualRateRange | None = None
    term_range_months: TermRangeMonths | None = None
    policy_version: str = Field(min_length=1)
    queried_at: datetime

    @model_validator(mode="after")
    def validate_conditions(self) -> "PersonalizedProductConditions":
        if self.queried_at.tzinfo is None:
            raise ValueError("queriedAt must include a timezone")
        if not any(
            value is not None
            for value in (
                self.max_amount,
                self.annual_rate_range,
                self.term_range_months,
            )
        ):
            raise ValueError("personalized conditions require at least one value")
        return self


class ProductComparisonItem(ApiModel):
    product_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    eligibility_summary: str = Field(min_length=1)
    public_conditions: PublicProductConditions
    personalized_conditions: PersonalizedProductConditions | None = None
    condition_status: ProductConditionStatus | None = None
    condition_reason_code: str | None = None
    official_source: ProductOfficialSource
    product_version: str = Field(min_length=1)
    application_url: AnyHttpUrl | None = None
    application_reference: str | None = None
    final_approval_required: Literal[True] = True
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_personalized_state(self) -> "ProductComparisonItem":
        is_personalized = self.condition_status == ProductConditionStatus.PERSONALIZED_AVAILABLE
        if is_personalized != (self.personalized_conditions is not None):
            raise ValueError("personalized conditions must match conditionStatus")
        return self


class ProductComparisonResponse(ApiModel):
    session_id: str = Field(min_length=1)
    status: ComparisonStatus
    items: list[ProductComparisonItem]
    assembled_at: datetime
    catalog_snapshot_id: str | None = None
    condition_query_id: str | None = None
    reason_code: str | None = None
    sortable_fields: list[ComparisonSortField]
    null_placement: Literal["LAST"] = "LAST"
    initial_order: Literal["CATALOG_SOURCE"] = "CATALOG_SOURCE"
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_response(self) -> "ProductComparisonResponse":
        if self.assembled_at.tzinfo is None:
            raise ValueError("assembledAt must include a timezone")
        if self.status == ComparisonStatus.CATALOG_UNAVAILABLE:
            if self.items or not self.reason_code:
                raise ValueError("unavailable catalog requires a reason and no items")
            if self.condition_query_id is not None or self.sortable_fields:
                raise ValueError("unavailable catalog cannot expose conditions or sorts")
        elif self.catalog_snapshot_id is None:
            raise ValueError("comparison items require catalogSnapshotId")
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("comparison productId values must be unique")
        if (
            self.status in {ComparisonStatus.AVAILABLE, ComparisonStatus.PARTIAL}
            and self.condition_query_id is None
        ):
            raise ValueError("personalized comparison requires conditionQueryId")
        if self.status == ComparisonStatus.AVAILABLE and any(
            item.personalized_conditions is None for item in self.items
        ):
            raise ValueError("AVAILABLE comparison requires all personalized conditions")
        return self
