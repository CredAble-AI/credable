from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.assessment_review import AssessmentReviewTargetType
from app.schemas.base import ApiModel
from app.schemas.review_workflow import (
    UnderwriterReviewResultCode,
    UnderwriterReviewStatus,
)


class UnderwriterReviewTriggerType(StrEnum):
    EVIDENCE_QUALITY = "EVIDENCE_QUALITY"
    CUSTOMER_ASSESSMENT_REVIEW = "CUSTOMER_ASSESSMENT_REVIEW"


class UnderwriterReviewQueueItem(ApiModel):
    review_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    trigger_type: UnderwriterReviewTriggerType
    trigger_id: str = Field(min_length=1)
    evidence_type: str | None = Field(default=None, min_length=1)
    target_type: AssessmentReviewTargetType | None = None
    target_assessment_id: str | None = Field(default=None, min_length=1)
    reason_codes: list[str] = Field(min_length=1)
    requested_at: datetime
    data_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    status: UnderwriterReviewStatus = UnderwriterReviewStatus.PENDING
    result_code: UnderwriterReviewResultCode | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    demo_only: bool

    @model_validator(mode="after")
    def validate_review_item(self) -> "UnderwriterReviewQueueItem":
        if self.requested_at.tzinfo is None:
            raise ValueError("requestedAt must include a timezone")
        for value in (self.started_at, self.completed_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("review processing timestamps must include a timezone")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reasonCodes must be unique")
        evidence_trigger = self.trigger_type == UnderwriterReviewTriggerType.EVIDENCE_QUALITY
        if evidence_trigger != (self.evidence_type is not None):
            raise ValueError("Evidence quality review requires evidenceType")
        customer_trigger = (
            self.trigger_type == UnderwriterReviewTriggerType.CUSTOMER_ASSESSMENT_REVIEW
        )
        if customer_trigger != (
            self.target_type is not None and self.target_assessment_id is not None
        ):
            raise ValueError("customer review requires an assessment target")
        if self.status == UnderwriterReviewStatus.PENDING and any(
            value is not None for value in (self.result_code, self.started_at, self.completed_at)
        ):
            raise ValueError("PENDING queue item cannot have processing metadata")
        if self.status == UnderwriterReviewStatus.IN_REVIEW and (
            self.started_at is None or self.result_code is not None or self.completed_at is not None
        ):
            raise ValueError("IN_REVIEW queue item requires only startedAt")
        if self.status == UnderwriterReviewStatus.COMPLETED and (
            self.started_at is None or self.result_code is None or self.completed_at is None
        ):
            raise ValueError("COMPLETED queue item requires result metadata")
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completedAt cannot precede startedAt")
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


class UnderwriterReviewCompleteRequest(ApiModel):
    result_code: UnderwriterReviewResultCode


class UnderwriterReviewDetailResponse(ApiModel):
    review: UnderwriterReviewQueueItem
