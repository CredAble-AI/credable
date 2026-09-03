from datetime import date, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class CurrentDecision(StrEnum):
    DECLINED = "DECLINED"
    HELD = "HELD"


class BusinessType(StrEnum):
    SOLE_PROPRIETOR = "SOLE_PROPRIETOR"


class Industry(StrEnum):
    FOOD_SERVICE = "FOOD_SERVICE"


class ProductType(StrEnum):
    SMALL_BUSINESS_WORKING_CAPITAL = "SMALL_BUSINESS_WORKING_CAPITAL"


class Applicant(ApiModel):
    applicant_id: str
    business_name: str


class ApplicationInfo(ApiModel):
    business_type: BusinessType
    industry: Industry
    business_tenure_months: int = Field(ge=0)
    product_type: ProductType
    requested_amount_krw: int = Field(gt=0)


class SecondLookCase(ApiModel):
    case_id: str
    application_date: date
    feature_cutoff_at: datetime
    applicant: Applicant
    application: ApplicationInfo
    current_decision: CurrentDecision
    decline_reason_codes: list[str]
    demo_only: bool = True

    @model_validator(mode="after")
    def validate_feature_cutoff(self) -> "SecondLookCase":
        if self.feature_cutoff_at.tzinfo is None:
            raise ValueError("featureCutoffAt must include a timezone")
        if self.feature_cutoff_at.date() < self.application_date:
            raise ValueError("featureCutoffAt cannot precede applicationDate")
        return self


class CaseState(ApiModel):
    case: SecondLookCase


class DemoCaseDefinition(ApiModel):
    demo_case_id: str
    case: SecondLookCase


class DemoCaseCatalogData(ApiModel):
    data_version: str
    cases: list[DemoCaseDefinition]


class DemoCaseCreateRequest(ApiModel):
    demo_case_id: str


class DemoCaseCreateResponse(ApiModel):
    case_id: str
    case: SecondLookCase
