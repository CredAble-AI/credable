from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class BorrowerType(StrEnum):
    INDIVIDUAL = "INDIVIDUAL"
    SOLE_PROPRIETOR = "SOLE_PROPRIETOR"
    CORPORATION = "CORPORATION"


class BusinessLegalForm(StrEnum):
    SOLE_PROPRIETOR = "SOLE_PROPRIETOR"
    CORPORATION = "CORPORATION"


class BusinessStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    CLOSED = "CLOSED"


class BorrowerBusinessRoleType(StrEnum):
    OWNER = "OWNER"
    REPRESENTATIVE = "REPRESENTATIVE"
    BORROWER_ENTITY = "BORROWER_ENTITY"


class Borrower(ApiModel):
    borrower_id: str = Field(min_length=1)
    borrower_type: BorrowerType
    display_name: str = Field(min_length=1)


class Business(ApiModel):
    business_id: str = Field(min_length=1)
    legal_form: BusinessLegalForm
    display_name: str = Field(min_length=1)
    industry_code: str = Field(min_length=1)
    industry_code_system: str = Field(min_length=1)
    industry_name: str = Field(min_length=1)
    business_started_on: date
    status: BusinessStatus


class BorrowerBusinessRole(ApiModel):
    borrower_id: str = Field(min_length=1)
    business_id: str = Field(min_length=1)
    role_type: BorrowerBusinessRoleType
    is_primary: bool = True
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_effective_period(self) -> "BorrowerBusinessRole":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effectiveTo must not precede effectiveFrom")
        return self


class CustomerSubject(ApiModel):
    borrower: Borrower
    primary_business: Business | None = None
    business_role: BorrowerBusinessRole | None = None
    source_type: Literal["BANK_INTERNAL"] = "BANK_INTERNAL"
    as_of_date: date
    data_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_business_relationship(self) -> "CustomerSubject":
        if (self.primary_business is None) != (self.business_role is None):
            raise ValueError("primaryBusiness and businessRole must be provided together")
        if self.primary_business is None or self.business_role is None:
            return self
        if self.business_role.borrower_id != self.borrower.borrower_id:
            raise ValueError("businessRole borrowerId must match borrower")
        if self.business_role.business_id != self.primary_business.business_id:
            raise ValueError("businessRole businessId must match primaryBusiness")
        return self
