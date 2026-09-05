from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


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
    eligible_for_reassessment: bool
    checked_at: datetime
    submission_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_version: str = Field(min_length=1)
    quality_policy_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

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
        if self.status == EvidenceQualityStatus.ACCEPTED:
            if failed_codes or self.rejection_codes or not self.eligible_for_reassessment:
                raise ValueError("ACCEPTED quality must pass every check")
        elif (
            not failed_codes
            or self.rejection_codes != failed_codes
            or self.eligible_for_reassessment
        ):
            raise ValueError("REJECTED quality must preserve failed rationale codes")
        return self


class EvidenceQualityResponse(ApiModel):
    session_id: str = Field(min_length=1)
    quality: EvidenceQualityState | None


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
