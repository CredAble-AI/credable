from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.customer import (
    BorrowerBusinessRoleType,
    BusinessLegalForm,
    CustomerSubject,
)


class CustomerSessionStatus(StrEnum):
    CREATED = "CREATED"


class DemoProfile(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    business_borrower_type: BusinessLegalForm | None = None
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    scenario_label: str = Field(min_length=1)
    scenario_summary: str = Field(min_length=1)


class CustomerSession(ApiModel):
    session_id: str = Field(min_length=1)
    demo_profile: DemoProfile
    customer_subject: CustomerSubject | None = None
    status: CustomerSessionStatus = CustomerSessionStatus.CREATED
    created_at: datetime
    data_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_created_at(self) -> "CustomerSession":
        if self.created_at.tzinfo is None:
            raise ValueError("createdAt must include a timezone")
        return self


class CustomerSessionState(ApiModel):
    session: CustomerSession


class DemoProfileDefinition(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    business_borrower_type: BusinessLegalForm
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    scenario_label: str = Field(min_length=1)
    scenario_summary: str = Field(min_length=1)
    customer_subject: CustomerSubject

    @model_validator(mode="after")
    def validate_business_borrower_scope(self) -> "DemoProfileDefinition":
        subject = self.customer_subject
        business = subject.primary_business
        role = subject.business_role
        if business is None or role is None:
            raise ValueError("registered primaryBusiness and businessRole are required")
        if subject.borrower.borrower_type.value != self.business_borrower_type.value:
            raise ValueError("borrowerType must match businessBorrowerType")
        if business.legal_form != self.business_borrower_type:
            raise ValueError("primaryBusiness legalForm must match businessBorrowerType")

        expected_role = (
            BorrowerBusinessRoleType.OWNER
            if self.business_borrower_type == BusinessLegalForm.SOLE_PROPRIETOR
            else BorrowerBusinessRoleType.BORROWER_ENTITY
        )
        if role.role_type != expected_role:
            raise ValueError("businessRole roleType must match businessBorrowerType")
        return self

    def to_profile(self) -> DemoProfile:
        return DemoProfile(
            demo_profile_id=self.demo_profile_id,
            business_borrower_type=self.business_borrower_type,
            display_name=self.display_name,
            description=self.description,
            scenario_label=self.scenario_label,
            scenario_summary=self.scenario_summary,
        )


class DemoProfileCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    profiles: list[DemoProfileDefinition] = Field(min_length=1)


class DemoProfileCatalogResponse(ApiModel):
    data_version: str = Field(min_length=1)
    profiles: list[DemoProfile] = Field(min_length=1)
    demo_only: Literal[True] = True


class DemoSessionCreateRequest(ApiModel):
    demo_profile_id: str | None = Field(default=None, min_length=1)
    business_borrower_type: BusinessLegalForm | None = None

    @model_validator(mode="after")
    def validate_single_demo_selector(self) -> "DemoSessionCreateRequest":
        selectors = (self.demo_profile_id is not None) + (self.business_borrower_type is not None)
        if selectors != 1:
            raise ValueError(
                "exactly one of demoProfileId or businessBorrowerType must be provided"
            )
        return self


class DemoSessionCreateResponse(ApiModel):
    session_id: str
    session: CustomerSession
