from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.evidence_trust import EvidenceTrustVerification


class EvidenceQualityDimension(StrEnum):
    PROVENANCE = "PROVENANCE"
    FRESHNESS = "FRESHNESS"
    AUTHENTICITY = "AUTHENTICITY"
    COMPLETENESS = "COMPLETENESS"
    CONSISTENCY = "CONSISTENCY"
    MANIPULATION_RISK = "MANIPULATION_RISK"


class EvidenceQualityDimensionStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_VERIFIED = "NOT_VERIFIED"


class EvidenceQualityStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class EvidenceQualityNextAction(StrEnum):
    RUN_REASSESSMENT = "RUN_REASSESSMENT"
    EXCLUDE_EVIDENCE = "EXCLUDE_EVIDENCE"
    UNDERWRITER_REVIEW = "UNDERWRITER_REVIEW"


class EvidenceQualityDimensionResult(ApiModel):
    dimension: EvidenceQualityDimension
    status: EvidenceQualityDimensionStatus
    rationale_code: str = Field(min_length=1)


class EvidenceQualityState(ApiModel):
    quality_check_id: str = Field(min_length=1)
    submission_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    status: EvidenceQualityStatus
    checks: list[EvidenceQualityDimensionResult]
    rejection_codes: list[str]
    suspicion_codes: list[str] = Field(default_factory=list)
    eligible_for_reassessment: bool
    next_action: EvidenceQualityNextAction
    underwriter_required: bool = False
    checked_at: datetime
    submission_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_version: str = Field(min_length=1)
    quality_policy_version: str = Field(min_length=1)
    trust_verification: EvidenceTrustVerification | None = None
    demo_only: Literal[True] = True

    @model_validator(mode="before")
    @classmethod
    def add_backward_compatible_routing_defaults(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        values = dict(data)
        status = values.get("status")
        use_aliases = "qualityCheckId" in values
        suspicion_key = "suspicionCodes" if use_aliases else "suspicion_codes"
        next_action_key = "nextAction" if use_aliases else "next_action"
        underwriter_key = "underwriterRequired" if use_aliases else "underwriter_required"
        values.setdefault(suspicion_key, [])
        if "nextAction" not in values and "next_action" not in values:
            values[next_action_key] = (
                EvidenceQualityNextAction.RUN_REASSESSMENT
                if status == EvidenceQualityStatus.ACCEPTED
                else EvidenceQualityNextAction.EXCLUDE_EVIDENCE
            )
        values.setdefault(underwriter_key, False)
        return values

    @model_validator(mode="after")
    def validate_quality_state(self) -> "EvidenceQualityState":
        if self.checked_at.tzinfo is None:
            raise ValueError("checkedAt must include a timezone")
        dimensions = [item.dimension for item in self.checks]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("quality dimensions must be unique")
        if set(dimensions) != set(EvidenceQualityDimension):
            raise ValueError("quality check must contain every required dimension")
        failed_codes = [
            item.rationale_code
            for item in self.checks
            if item.status != EvidenceQualityDimensionStatus.PASSED
        ]
        if self.rejection_codes != failed_codes:
            raise ValueError("quality must preserve non-passed rationale codes")
        if not set(self.suspicion_codes).issubset(self.rejection_codes):
            raise ValueError("suspicion codes must be included in rejection codes")
        if self.status == EvidenceQualityStatus.ACCEPTED:
            if (
                failed_codes
                or self.suspicion_codes
                or not self.eligible_for_reassessment
                or self.next_action != EvidenceQualityNextAction.RUN_REASSESSMENT
                or self.underwriter_required
            ):
                raise ValueError("ACCEPTED quality must pass every check")
        elif self.status == EvidenceQualityStatus.REJECTED:
            if (
                not failed_codes
                or self.suspicion_codes
                or self.eligible_for_reassessment
                or self.next_action != EvidenceQualityNextAction.EXCLUDE_EVIDENCE
                or self.underwriter_required
            ):
                raise ValueError("REJECTED quality must exclude failed Evidence")
        elif (
            not failed_codes
            or not self.suspicion_codes
            or self.eligible_for_reassessment
            or self.next_action != EvidenceQualityNextAction.UNDERWRITER_REVIEW
            or not self.underwriter_required
        ):
            raise ValueError("REVIEW_REQUIRED quality must route to an underwriter")
        return self


class EvidenceQualityResponse(ApiModel):
    session_id: str = Field(min_length=1)
    quality: EvidenceQualityState | None
    underwriter_review_id: str | None = Field(default=None, min_length=1)


class DemoEvidenceQualityDefinition(ApiModel):
    evidence_type: str = Field(min_length=1)
    checks: list[EvidenceQualityDimensionResult]

    @model_validator(mode="after")
    def validate_checks(self) -> "DemoEvidenceQualityDefinition":
        dimensions = [item.dimension for item in self.checks]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("Demo quality dimensions must be unique")
        if set(dimensions) != set(EvidenceQualityDimension):
            raise ValueError("Demo quality result must contain every required dimension")
        return self


class DemoEvidenceQualityCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    quality_policy_version: str = Field(min_length=1)
    results: list[DemoEvidenceQualityDefinition] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_types(self) -> "DemoEvidenceQualityCatalogData":
        evidence_types = [item.evidence_type for item in self.results]
        if len(evidence_types) != len(set(evidence_types)):
            raise ValueError("quality evidenceType values must be unique")
        return self
