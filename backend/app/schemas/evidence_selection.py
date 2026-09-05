from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType
from app.schemas.evidence_consent import EvidenceConsentScopeDefinition
from app.schemas.evidence_file import EvidenceCollectionMode


class EvidenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    REQUESTABLE = "REQUESTABLE"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceSelectionStatus(StrEnum):
    SELECTED = "SELECTED"
    NOT_REQUIRED = "NOT_REQUIRED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class EvidenceCandidateDefinition(ApiModel):
    evidence_type: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_type: ConsentSourceType
    collection_mode: EvidenceCollectionMode
    boundary_codes: list[str] = Field(min_length=1)
    boundary_resolution_value: float = Field(ge=0, le=1)
    quality_reliability: float = Field(ge=0, le=1)
    customer_effort: float = Field(ge=0, le=1)
    privacy_sensitivity: float = Field(ge=0, le=1)
    acquisition_delay: float = Field(ge=0, le=1)
    acquisition_cost: float = Field(ge=0, le=1)
    rationale_codes: list[str] = Field(min_length=1)
    consent_scope: EvidenceConsentScopeDefinition

    @model_validator(mode="after")
    def validate_unique_codes(self) -> "EvidenceCandidateDefinition":
        if len(self.boundary_codes) != len(set(self.boundary_codes)):
            raise ValueError("boundaryCodes values must be unique")
        if len(self.rationale_codes) != len(set(self.rationale_codes)):
            raise ValueError("rationaleCodes values must be unique")
        return self


class SelectedEvidenceCandidate(ApiModel):
    evidence_type: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_type: ConsentSourceType
    collection_mode: EvidenceCollectionMode | None = None
    availability: EvidenceAvailability
    rationale_codes: list[str] = Field(min_length=1)
    consent_scope: EvidenceConsentScopeDefinition | None = None
    demo_only: Literal[True] = True


class EvidenceSelectionState(ApiModel):
    selection_id: str = Field(min_length=1)
    boundary_check_id: str = Field(min_length=1)
    resolution_id: str | None = Field(default=None, min_length=1)
    iteration: int = Field(ge=1)
    status: EvidenceSelectionStatus
    selected_evidence: SelectedEvidenceCandidate | None = None
    evaluated_candidate_count: int = Field(ge=0)
    stop_reason: str | None = None
    underwriter_required: bool
    selected_at: datetime
    calibration_version: str = Field(min_length=1)
    boundary_policy_version: str = Field(min_length=1)
    selection_policy_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_state(self) -> "EvidenceSelectionState":
        if self.selected_at.tzinfo is None:
            raise ValueError("selectedAt must include a timezone")
        if self.iteration == 1 and self.resolution_id is not None:
            raise ValueError("first selection cannot reference an Evidence resolution")
        if self.iteration > 1 and self.resolution_id is None:
            raise ValueError("repeated selection requires an Evidence resolution")
        if self.status == EvidenceSelectionStatus.SELECTED:
            if self.selected_evidence is None:
                raise ValueError("SELECTED state requires selectedEvidence")
            if self.stop_reason is not None or self.underwriter_required:
                raise ValueError("SELECTED state must continue without a stop reason")
        elif self.selected_evidence is not None:
            raise ValueError("stopped selection cannot include selectedEvidence")
        elif self.status == EvidenceSelectionStatus.NOT_REQUIRED:
            if self.stop_reason != "PATH_STABLE" or self.underwriter_required:
                raise ValueError("NOT_REQUIRED state must stop on PATH_STABLE")
        elif not self.stop_reason or not self.underwriter_required:
            raise ValueError("blocked selection requires a stop reason and review")
        return self


class EvidenceSelectionResponse(ApiModel):
    session_id: str = Field(min_length=1)
    selection: EvidenceSelectionState | None


class DemoEvidenceCandidateCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    selection_policy_version: str = Field(min_length=1)
    candidates: list[EvidenceCandidateDefinition] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_types(self) -> "DemoEvidenceCandidateCatalogData":
        evidence_types = [item.evidence_type for item in self.candidates]
        if len(evidence_types) != len(set(evidence_types)):
            raise ValueError("candidate evidenceType values must be unique")
        return self
