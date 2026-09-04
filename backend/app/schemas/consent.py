from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class ConsentSourceType(StrEnum):
    BANK_INTERNAL = "BANK_INTERNAL"
    CREDIT_INFORMATION = "CREDIT_INFORMATION"
    CUSTOMER_SUBMITTED = "CUSTOMER_SUBMITTED"
    EXTERNAL_CONNECTED = "EXTERNAL_CONNECTED"


class ConsentStatus(StrEnum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"


class ConsentScopeDefinition(ApiModel):
    source_type: ConsentSourceType
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool | None = None


class ConsentScopeCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    scopes: list[ConsentScopeDefinition] = Field(min_length=1)


class ConsentState(ApiModel):
    source_type: ConsentSourceType
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool | None = None
    status: ConsentStatus
    granted_at: datetime | None = None
    withdrawn_at: datetime | None = None
    updated_at: datetime | None = None
    scope_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_timestamps(self) -> "ConsentState":
        timestamps = (self.granted_at, self.withdrawn_at, self.updated_at)
        if any(value is not None and value.tzinfo is None for value in timestamps):
            raise ValueError("consent timestamps must include a timezone")
        if self.status == ConsentStatus.PENDING and any(timestamps):
            raise ValueError("PENDING consent cannot have action timestamps")
        if self.status == ConsentStatus.GRANTED:
            if self.granted_at is None or self.updated_at is None:
                raise ValueError("GRANTED consent requires grantedAt and updatedAt")
            if self.withdrawn_at is not None:
                raise ValueError("GRANTED consent cannot have withdrawnAt")
        if self.status == ConsentStatus.WITHDRAWN and None in (
            self.granted_at,
            self.withdrawn_at,
            self.updated_at,
        ):
            raise ValueError("WITHDRAWN consent requires all action timestamps")
        return self


class ConsentListResponse(ApiModel):
    session_id: str = Field(min_length=1)
    consents: list[ConsentState]
    scope_version: str = Field(min_length=1)
    demo_only: Literal[True] = True
