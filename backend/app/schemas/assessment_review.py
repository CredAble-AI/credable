from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.review_workflow import CustomerReviewProcessing


class AssessmentReviewTargetType(StrEnum):
    BASELINE_ASSESSMENT = "BASELINE_ASSESSMENT"
    SUPPLEMENTAL_ASSESSMENT = "SUPPLEMENTAL_ASSESSMENT"


class CustomerAssessmentReviewReason(StrEnum):
    """What the customer says is wrong, so review looks only at that."""

    INCORRECT_INFORMATION = "INCORRECT_INFORMATION"
    MISSING_RECENT_INFORMATION = "MISSING_RECENT_INFORMATION"
    EXCLUDED_EVIDENCE_DISPUTED = "EXCLUDED_EVIDENCE_DISPUTED"


class AssessmentReviewRequestCreateRequest(ApiModel):
    customer_reason_code: CustomerAssessmentReviewReason


class AssessmentReviewRequestState(ApiModel):
    review_request_id: str = Field(min_length=1)
    target_type: AssessmentReviewTargetType
    target_assessment_id: str = Field(min_length=1)
    reason_code: Literal["CUSTOMER_REQUESTED_ASSESSMENT_REVIEW"] = (
        "CUSTOMER_REQUESTED_ASSESSMENT_REVIEW"
    )
    # Requests stored before customers could state a reason read back as None.
    customer_reason_code: CustomerAssessmentReviewReason | None = None
    requested_at: datetime
    request_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    request_policy_version: Literal["assessment-review-request-policy-v1"] = (
        "assessment-review-request-policy-v1"
    )
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_requested_at(self) -> "AssessmentReviewRequestState":
        if self.requested_at.tzinfo is None:
            raise ValueError("requestedAt must include a timezone")
        return self


class AssessmentReviewRequestResponse(ApiModel):
    session_id: str = Field(min_length=1)
    review_request: AssessmentReviewRequestState | None
    underwriter_review_id: str | None = Field(default=None, min_length=1)
    processing: CustomerReviewProcessing | None = None
