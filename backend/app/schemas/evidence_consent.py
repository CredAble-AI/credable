from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType, ConsentStatus


class EvidenceConsentScopeDefinition(ApiModel):
    scope_version: str = Field(min_length=1)
    purpose_code: str = Field(min_length=1)
    purpose_description: str = Field(min_length=1)
    data_categories: list[str] = Field(min_length=1)
    period_start: date
    period_end: date
    required: Literal[True] = True

    @model_validator(mode="after")
    def validate_scope(self) -> "EvidenceConsentScopeDefinition":
        if self.period_end < self.period_start:
            raise ValueError("periodEnd must not precede periodStart")
        if len(self.data_categories) != len(set(self.data_categories)):
            raise ValueError("consent dataCategories values must be unique")
        if any(not category.strip() for category in self.data_categories):
            raise ValueError("consent dataCategories values cannot be blank")
        return self


class EvidenceConsentState(ApiModel):
    evidence_consent_id: str = Field(min_length=1)
    selection_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    source_type: ConsentSourceType
    purpose_code: str = Field(min_length=1)
    purpose_description: str = Field(min_length=1)
    data_categories: list[str] = Field(min_length=1)
    period_start: date
    period_end: date
    required: Literal[True] = True
    status: ConsentStatus
    granted_at: datetime | None = None
    withdrawn_at: datetime | None = None
    updated_at: datetime | None = None
    scope_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_state(self) -> "EvidenceConsentState":
        if self.period_end < self.period_start:
            raise ValueError("periodEnd must not precede periodStart")
        if len(self.data_categories) != len(set(self.data_categories)):
            raise ValueError("dataCategories values must be unique")
        timestamps = (self.granted_at, self.withdrawn_at, self.updated_at)
        if any(value is not None and value.tzinfo is None for value in timestamps):
            raise ValueError("Evidence consent timestamps must include a timezone")
        if self.status == ConsentStatus.PENDING and any(timestamps):
            raise ValueError("PENDING Evidence consent cannot have action timestamps")
        if self.status == ConsentStatus.GRANTED:
            if self.granted_at is None or self.updated_at is None:
                raise ValueError("GRANTED Evidence consent requires action timestamps")
            if self.withdrawn_at is not None:
                raise ValueError("GRANTED Evidence consent cannot have withdrawnAt")
        if self.status == ConsentStatus.WITHDRAWN and None in timestamps:
            raise ValueError("WITHDRAWN Evidence consent requires all action timestamps")
        return self


class EvidenceConsentResponse(ApiModel):
    session_id: str = Field(min_length=1)
    selection_id: str = Field(min_length=1)
    consent: EvidenceConsentState
