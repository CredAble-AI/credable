from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class UnderwriterReviewStatus(StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED = "COMPLETED"


class UnderwriterReviewResultCode(StrEnum):
    EVIDENCE_CONFIRMED = "EVIDENCE_CONFIRMED"
    EVIDENCE_EXCLUDED = "EVIDENCE_EXCLUDED"
    ASSESSMENT_CONFIRMED = "ASSESSMENT_CONFIRMED"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    ADDITIONAL_INFORMATION_REQUIRED = "ADDITIONAL_INFORMATION_REQUIRED"
    ESCALATED = "ESCALATED"


class UnderwriterReviewWorkflowState(ApiModel):
    review_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    trigger_type: Literal["EVIDENCE_QUALITY", "CUSTOMER_ASSESSMENT_REVIEW"]
    trigger_id: str = Field(min_length=1)
    status: UnderwriterReviewStatus
    result_code: UnderwriterReviewResultCode | None = None
    reviewer_principal: Literal["demo-underwriter"] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    workflow_policy_version: Literal["underwriter-review-workflow-v1"] = (
        "underwriter-review-workflow-v1"
    )
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_workflow(self) -> "UnderwriterReviewWorkflowState":
        for field_name, value in (
            ("startedAt", self.started_at),
            ("completedAt", self.completed_at),
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{field_name} must include a timezone")
        if self.status == UnderwriterReviewStatus.PENDING:
            if any(
                value is not None
                for value in (
                    self.result_code,
                    self.reviewer_principal,
                    self.started_at,
                    self.completed_at,
                )
            ):
                raise ValueError("PENDING review cannot contain processing metadata")
        elif self.status == UnderwriterReviewStatus.IN_REVIEW:
            if (
                self.reviewer_principal is None
                or self.started_at is None
                or self.result_code is not None
                or self.completed_at is not None
            ):
                raise ValueError("IN_REVIEW requires only reviewer and start time")
        elif (
            self.reviewer_principal is None
            or self.started_at is None
            or self.result_code is None
            or self.completed_at is None
            or self.completed_at < self.started_at
        ):
            raise ValueError("COMPLETED review requires an ordered result lifecycle")
        return self


class CustomerReviewProcessing(ApiModel):
    status: UnderwriterReviewStatus
    result_code: UnderwriterReviewResultCode | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_public_state(self) -> "CustomerReviewProcessing":
        for value in (self.started_at, self.completed_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("processing timestamps must include a timezone")
        if self.status == UnderwriterReviewStatus.PENDING:
            if any(
                value is not None
                for value in (self.result_code, self.started_at, self.completed_at)
            ):
                raise ValueError("PENDING processing cannot have result metadata")
        elif self.status == UnderwriterReviewStatus.IN_REVIEW:
            if (
                self.started_at is None
                or self.result_code is not None
                or self.completed_at is not None
            ):
                raise ValueError("IN_REVIEW processing requires only startedAt")
        elif (
            self.started_at is None
            or self.result_code is None
            or self.completed_at is None
            or self.completed_at < self.started_at
        ):
            raise ValueError("COMPLETED processing requires an ordered result")
        return self
