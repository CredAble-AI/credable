from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class UnderwriterReviewTriggerType(StrEnum):
    EVIDENCE_QUALITY = "EVIDENCE_QUALITY"


class UnderwriterReviewQueueItem(ApiModel):
    review_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    trigger_type: Literal[UnderwriterReviewTriggerType.EVIDENCE_QUALITY]
    trigger_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    reason_codes: list[str] = Field(min_length=1)
    requested_at: datetime
    data_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    demo_only: bool

    @model_validator(mode="after")
    def validate_review_item(self) -> "UnderwriterReviewQueueItem":
        if self.requested_at.tzinfo is None:
            raise ValueError("requestedAt must include a timezone")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reasonCodes must be unique")
        return self


class UnderwriterReviewQueueResponse(ApiModel):
    total_count: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    items: list[UnderwriterReviewQueueItem]
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_page(self) -> "UnderwriterReviewQueueResponse":
        if len(self.items) > self.limit:
            raise ValueError("items cannot exceed limit")
        if self.items and self.offset + len(self.items) > self.total_count:
            raise ValueError("page cannot exceed totalCount")
        return self
