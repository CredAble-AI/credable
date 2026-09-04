from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class CustomerSessionStatus(StrEnum):
    CREATED = "CREATED"


class DemoProfile(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class CustomerSession(ApiModel):
    session_id: str = Field(min_length=1)
    demo_profile: DemoProfile
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
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)

    def to_profile(self) -> DemoProfile:
        return DemoProfile(
            demo_profile_id=self.demo_profile_id,
            display_name=self.display_name,
            description=self.description,
        )


class DemoProfileCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    profiles: list[DemoProfileDefinition] = Field(min_length=1)


class DemoProfileCatalogResponse(ApiModel):
    data_version: str = Field(min_length=1)
    profiles: list[DemoProfile] = Field(min_length=1)
    demo_only: Literal[True] = True


class DemoSessionCreateRequest(ApiModel):
    demo_profile_id: str = Field(min_length=1)


class DemoSessionCreateResponse(ApiModel):
    session_id: str
    session: CustomerSession
