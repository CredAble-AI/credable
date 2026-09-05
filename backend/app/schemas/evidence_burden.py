from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType
from app.schemas.policy_boundary import EvidenceResolutionStatus


class EvidenceTypeBurdenBreakdown(ApiModel):
    evidence_type: str = Field(min_length=1)
    source_type: ConsentSourceType
    request_count: int = Field(ge=1)
    submission_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    first_requested_at: datetime
    last_requested_at: datetime

    @model_validator(mode="after")
    def validate_breakdown(self) -> "EvidenceTypeBurdenBreakdown":
        if self.first_requested_at.tzinfo is None or self.last_requested_at.tzinfo is None:
            raise ValueError("Evidence burden timestamps must include a timezone")
        if self.first_requested_at > self.last_requested_at:
            raise ValueError("firstRequestedAt cannot exceed lastRequestedAt")
        if self.submission_count > self.request_count:
            raise ValueError("submissionCount cannot exceed requestCount")
        if self.accepted_count + self.rejected_count > self.submission_count:
            raise ValueError("quality result count cannot exceed submissionCount")
        return self


class AdminEvidenceBurdenResponse(ApiModel):
    session_id: str = Field(min_length=1)
    as_of: datetime
    evidence_request_count: int = Field(ge=0)
    repeated_request_count: int = Field(ge=0)
    available_request_count: int = Field(ge=0)
    requestable_request_count: int = Field(ge=0)
    consent_required_request_count: int = Field(ge=0)
    unavailable_request_count: int = Field(ge=0)
    submission_count: int = Field(ge=0)
    pending_submission_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    unverified_submission_count: int = Field(ge=0)
    failed_quality_dimension_count: int = Field(ge=0)
    supplemental_assessment_count: int = Field(ge=0)
    resolution_count: int = Field(ge=0)
    latest_resolution_status: EvidenceResolutionStatus | None
    collection_stopped: bool | None
    max_request_iteration: int = Field(ge=0)
    evidence_types: list[EvidenceTypeBurdenBreakdown]
    measurement_version: Literal["evidence-burden-metrics-v1"] = "evidence-burden-metrics-v1"
    policy_threshold_applied: Literal[False] = False
    demo_only: bool

    @model_validator(mode="after")
    def validate_totals(self) -> "AdminEvidenceBurdenResponse":
        availability_total = (
            self.available_request_count
            + self.requestable_request_count
            + self.consent_required_request_count
            + self.unavailable_request_count
        )
        if availability_total != self.evidence_request_count:
            raise ValueError("request availability counts must equal evidenceRequestCount")
        if self.repeated_request_count > self.evidence_request_count:
            raise ValueError("repeatedRequestCount cannot exceed evidenceRequestCount")
        if self.submission_count + self.pending_submission_count != self.evidence_request_count:
            raise ValueError("submission counts must equal evidenceRequestCount")
        if (
            self.accepted_count + self.rejected_count + self.unverified_submission_count
            != self.submission_count
        ):
            raise ValueError("quality counts must equal submissionCount")
        if self.as_of.tzinfo is None:
            raise ValueError("asOf must include a timezone")
        if self.resolution_count == 0 and (
            self.latest_resolution_status is not None or self.collection_stopped is not None
        ):
            raise ValueError("resolution state requires a stored resolution")
        if self.resolution_count > 0 and (
            self.latest_resolution_status is None or self.collection_stopped is None
        ):
            raise ValueError("stored resolution requires its latest state")
        return self
