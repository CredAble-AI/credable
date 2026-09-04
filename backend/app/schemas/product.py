from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import AnyHttpUrl, Field, model_validator

from app.schemas.base import ApiModel

DECIMAL_PATTERN = r"^(0|[1-9]\d*)(\.\d+)?$"


class ProductCatalogStatus(StrEnum):
    NOT_LOADED = "NOT_LOADED"
    CATALOG_NOT_CONFIGURED = "CATALOG_NOT_CONFIGURED"
    AVAILABLE = "AVAILABLE"
    FAILED = "FAILED"


class MoneyAmount(ApiModel):
    amount: str = Field(pattern=DECIMAL_PATTERN)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")


class AnnualRateRange(ApiModel):
    min_percent: str = Field(pattern=DECIMAL_PATTERN)
    max_percent: str = Field(pattern=DECIMAL_PATTERN)

    @model_validator(mode="after")
    def validate_range(self) -> "AnnualRateRange":
        if Decimal(self.min_percent) > Decimal(self.max_percent):
            raise ValueError("minPercent cannot exceed maxPercent")
        return self


class TermRangeMonths(ApiModel):
    min_months: int = Field(ge=1)
    max_months: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "TermRangeMonths":
        if self.min_months > self.max_months:
            raise ValueError("minMonths cannot exceed maxMonths")
        return self


class ProductOfficialSource(ApiModel):
    source_name: str = Field(min_length=1)
    source_url: AnyHttpUrl | None = None
    effective_date: date


class BankProduct(ApiModel):
    product_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    eligibility_summary: str = Field(min_length=1)
    public_max_amount: MoneyAmount | None = None
    annual_rate_range: AnnualRateRange | None = None
    term_range_months: TermRangeMonths | None = None
    repayment_methods: list[str]
    official_source: ProductOfficialSource
    product_version: str = Field(min_length=1)
    application_url: AnyHttpUrl | None = None
    application_reference: str | None = None
    demo_only: Literal[True] = True


class ProductCatalogAdapterResult(ApiModel):
    status: ProductCatalogStatus
    products: list[BankProduct] = Field(default_factory=list)
    catalog_version: str | None = None
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "ProductCatalogAdapterResult":
        product_ids = [item.product_id for item in self.products]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("productId values must be unique")
        if self.status == ProductCatalogStatus.NOT_LOADED:
            raise ValueError("catalog adapter cannot return NOT_LOADED")
        if self.status == ProductCatalogStatus.AVAILABLE:
            if self.catalog_version is None:
                raise ValueError("AVAILABLE catalog requires catalogVersion")
            if self.reason_code is not None:
                raise ValueError("AVAILABLE catalog cannot have reasonCode")
        else:
            if self.products or self.catalog_version is not None:
                raise ValueError("unavailable catalog cannot contain products or version")
            if not self.reason_code:
                raise ValueError("unavailable catalog requires reasonCode")
        return self


class ProductCatalogState(ApiModel):
    status: ProductCatalogStatus
    catalog_snapshot_id: str | None = None
    products: list[BankProduct] = Field(default_factory=list)
    retrieved_at: datetime | None = None
    catalog_version: str | None = None
    reason_code: str | None = None
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_state(self) -> "ProductCatalogState":
        if self.retrieved_at is not None and self.retrieved_at.tzinfo is None:
            raise ValueError("retrievedAt must include a timezone")
        if self.status == ProductCatalogStatus.NOT_LOADED:
            if self.catalog_snapshot_id is not None or self.retrieved_at is not None:
                raise ValueError("NOT_LOADED catalog cannot have retrieval metadata")
            if self.products or self.catalog_version is not None or self.reason_code:
                raise ValueError("NOT_LOADED catalog cannot have result data")
            return self
        if self.catalog_snapshot_id is None or self.retrieved_at is None:
            raise ValueError("loaded catalog requires retrieval metadata")
        ProductCatalogAdapterResult(
            status=self.status,
            products=self.products,
            catalog_version=self.catalog_version,
            reason_code=self.reason_code,
        )
        return self


class ProductCatalogResponse(ApiModel):
    session_id: str = Field(min_length=1)
    catalog: ProductCatalogState
