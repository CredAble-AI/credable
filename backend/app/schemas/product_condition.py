from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.assessment import AssessmentState
from app.schemas.base import ApiModel
from app.schemas.data_source import DataSourceState
from app.schemas.product import AnnualRateRange, BankProduct, MoneyAmount, TermRangeMonths


class ProductConditionQueryStatus(StrEnum):
    NOT_QUERIED = "NOT_QUERIED"
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ProductConditionStatus(StrEnum):
    PUBLIC_ONLY = "PUBLIC_ONLY"
    PERSONALIZED_AVAILABLE = "PERSONALIZED_AVAILABLE"
    INELIGIBLE = "INELIGIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    POLICY_NOT_CONFIGURED = "POLICY_NOT_CONFIGURED"
    QUERY_FAILED = "QUERY_FAILED"


class ProductConditionAdapterInput(ApiModel):
    session_id: str = Field(min_length=1)
    product: BankProduct
    catalog_snapshot_id: str = Field(min_length=1)
    assessment: AssessmentState
    data_sources: list[DataSourceState]
    data_snapshot_id: str = Field(min_length=1)
    demo_only: Literal[True] = True


class ProductConditionAdapterResult(ApiModel):
    status: ProductConditionStatus
    personalized_max_amount: MoneyAmount | None = None
    personalized_annual_rate_range: AnnualRateRange | None = None
    personalized_term_range_months: TermRangeMonths | None = None
    policy_version: str | None = None
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "ProductConditionAdapterResult":
        personalized_values = (
            self.personalized_max_amount,
            self.personalized_annual_rate_range,
            self.personalized_term_range_months,
        )
        if self.status == ProductConditionStatus.PERSONALIZED_AVAILABLE:
            if not any(value is not None for value in personalized_values):
                raise ValueError("personalized result requires at least one condition")
            if self.policy_version is None:
                raise ValueError("personalized result requires policyVersion")
            if self.reason_code is not None:
                raise ValueError("personalized result cannot have reasonCode")
        elif any(value is not None for value in personalized_values):
            raise ValueError("non-personalized result cannot contain personalized values")
        if (
            self.status
            in {
                ProductConditionStatus.INELIGIBLE,
                ProductConditionStatus.INSUFFICIENT_DATA,
                ProductConditionStatus.POLICY_NOT_CONFIGURED,
                ProductConditionStatus.QUERY_FAILED,
            }
            and not self.reason_code
        ):
            raise ValueError("unavailable product condition requires reasonCode")
        if self.status == ProductConditionStatus.INELIGIBLE and self.policy_version is None:
            raise ValueError("ineligible result requires policyVersion")
        return self


class ProductCondition(ApiModel):
    product_id: str = Field(min_length=1)
    status: ProductConditionStatus
    personalized_max_amount: MoneyAmount | None = None
    personalized_annual_rate_range: AnnualRateRange | None = None
    personalized_term_range_months: TermRangeMonths | None = None
    policy_version: str | None = None
    queried_at: datetime
    reason_code: str | None = None
    final_approval_required: Literal[True] = True
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_condition(self) -> "ProductCondition":
        if self.queried_at.tzinfo is None:
            raise ValueError("queriedAt must include a timezone")
        ProductConditionAdapterResult(
            status=self.status,
            personalized_max_amount=self.personalized_max_amount,
            personalized_annual_rate_range=self.personalized_annual_rate_range,
            personalized_term_range_months=self.personalized_term_range_months,
            policy_version=self.policy_version,
            reason_code=self.reason_code,
        )
        return self


class ProductConditionInputSnapshot(ApiModel):
    catalog_snapshot_id: str = Field(min_length=1)
    products: list[BankProduct]
    assessment: AssessmentState
    data_sources: list[DataSourceState]
    data_snapshot_id: str = Field(min_length=1)
    demo_only: Literal[True] = True


class ProductConditionQueryState(ApiModel):
    query_id: str | None = None
    status: ProductConditionQueryStatus
    conditions: list[ProductCondition] = Field(default_factory=list)
    queried_at: datetime | None = None
    catalog_snapshot_id: str | None = None
    assessment_id: str | None = None
    data_snapshot_id: str | None = None
    reason_code: str | None = None
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_state(self) -> "ProductConditionQueryState":
        if self.queried_at is not None and self.queried_at.tzinfo is None:
            raise ValueError("queriedAt must include a timezone")
        execution_fields = (self.query_id, self.queried_at)
        if self.status == ProductConditionQueryStatus.NOT_QUERIED:
            all_metadata = execution_fields + (
                self.catalog_snapshot_id,
                self.assessment_id,
                self.data_snapshot_id,
            )
            if any(value is not None for value in all_metadata):
                raise ValueError("NOT_QUERIED state cannot have execution metadata")
            if self.conditions or self.reason_code:
                raise ValueError("NOT_QUERIED state cannot have results")
            return self
        if any(value is None for value in execution_fields):
            raise ValueError("queried state requires execution metadata")
        if self.status == ProductConditionQueryStatus.CATALOG_UNAVAILABLE:
            if (
                self.conditions
                or self.assessment_id is not None
                or self.data_snapshot_id is not None
                or not self.reason_code
            ):
                raise ValueError("unavailable catalog requires a reason and no conditions")
            return self
        if self.catalog_snapshot_id is None or self.data_snapshot_id is None:
            raise ValueError("condition results require catalog and data snapshots")
        failed_count = sum(
            item.status == ProductConditionStatus.QUERY_FAILED for item in self.conditions
        )
        if self.status == ProductConditionQueryStatus.COMPLETED and failed_count:
            raise ValueError("COMPLETED query cannot contain failed conditions")
        if self.status == ProductConditionQueryStatus.COMPLETED and self.reason_code:
            raise ValueError("COMPLETED query cannot have reasonCode")
        if self.status == ProductConditionQueryStatus.PARTIAL and not (
            0 < failed_count < len(self.conditions)
        ):
            raise ValueError("PARTIAL query requires mixed condition results")
        if self.status == ProductConditionQueryStatus.PARTIAL and not self.reason_code:
            raise ValueError("PARTIAL query requires reasonCode")
        if self.status == ProductConditionQueryStatus.FAILED and (
            not self.conditions or failed_count != len(self.conditions)
        ):
            raise ValueError("FAILED query requires all conditions to fail")
        if self.status == ProductConditionQueryStatus.FAILED and not self.reason_code:
            raise ValueError("FAILED query requires reasonCode")
        return self


class ProductConditionQueryResponse(ApiModel):
    session_id: str = Field(min_length=1)
    query: ProductConditionQueryState
