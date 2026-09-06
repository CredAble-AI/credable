from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType
from app.schemas.evidence_consent import EvidenceConsentScopeDefinition
from app.schemas.evidence_file import EvidenceCollectionMode
from app.schemas.feature_snapshot import FeatureCode


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
    applicable_information_gap_codes: list[str] = Field(min_length=1)
    information_content_codes: list[str] = Field(min_length=1)
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
        if len(self.applicable_information_gap_codes) != len(
            set(self.applicable_information_gap_codes)
        ):
            raise ValueError("applicableInformationGapCodes values must be unique")
        if len(self.information_content_codes) != len(set(self.information_content_codes)):
            raise ValueError("informationContentCodes values must be unique")
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
    matched_information_gap_codes: list[str] = Field(default_factory=list)
    information_content_codes: list[str] = Field(default_factory=list)
    novel_information_codes: list[str] = Field(default_factory=list)
    overlapping_information_codes: list[str] = Field(default_factory=list)
    consent_scope: EvidenceConsentScopeDefinition | None = None
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_information_gaps(self) -> "SelectedEvidenceCandidate":
        if len(self.matched_information_gap_codes) != len(set(self.matched_information_gap_codes)):
            raise ValueError("matchedInformationGapCodes values must be unique")
        information_codes = set(self.information_content_codes)
        novel_codes = set(self.novel_information_codes)
        overlapping_codes = set(self.overlapping_information_codes)
        if len(information_codes) != len(self.information_content_codes):
            raise ValueError("informationContentCodes values must be unique")
        if len(novel_codes) != len(self.novel_information_codes):
            raise ValueError("novelInformationCodes values must be unique")
        if len(overlapping_codes) != len(self.overlapping_information_codes):
            raise ValueError("overlappingInformationCodes values must be unique")
        if novel_codes.intersection(overlapping_codes):
            raise ValueError("novel and overlapping information codes cannot overlap")
        if (novel_codes or overlapping_codes) and novel_codes.union(
            overlapping_codes
        ) != information_codes:
            raise ValueError("novel and overlapping codes must partition information content")
        return self


class EvidenceSelectionState(ApiModel):
    selection_id: str = Field(min_length=1)
    boundary_check_id: str = Field(min_length=1)
    resolution_id: str | None = Field(default=None, min_length=1)
    rejected_quality_check_id: str | None = Field(default=None, min_length=1)
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
    source_credit_assessment_id: str | None = Field(default=None, min_length=1)
    information_gap_codes: list[str] = Field(default_factory=list)
    baseline_feature_snapshot_id: str | None = Field(default=None, min_length=1)
    baseline_information_coverage_codes: list[str] = Field(default_factory=list)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_state(self) -> "EvidenceSelectionState":
        if self.selected_at.tzinfo is None:
            raise ValueError("selectedAt must include a timezone")
        if len(self.information_gap_codes) != len(set(self.information_gap_codes)):
            raise ValueError("informationGapCodes values must be unique")
        if self.source_credit_assessment_id is None and self.information_gap_codes:
            raise ValueError("informationGapCodes require sourceCreditAssessmentId")
        if len(self.baseline_information_coverage_codes) != len(
            set(self.baseline_information_coverage_codes)
        ):
            raise ValueError("baselineInformationCoverageCodes values must be unique")
        if self.baseline_feature_snapshot_id is None and self.baseline_information_coverage_codes:
            raise ValueError("baseline coverage requires baselineFeatureSnapshotId")
        repeated_lineage = [self.resolution_id, self.rejected_quality_check_id]
        if self.iteration == 1 and any(repeated_lineage):
            raise ValueError("first selection cannot reference repeated-selection lineage")
        if self.iteration > 1 and sum(item is not None for item in repeated_lineage) != 1:
            raise ValueError("repeated selection requires exactly one lineage reference")
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


class BaselineInformationCoverageRule(ApiModel):
    information_content_code: str = Field(min_length=1)
    required_feature_codes: list[FeatureCode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_features(self) -> "BaselineInformationCoverageRule":
        if len(self.required_feature_codes) != len(set(self.required_feature_codes)):
            raise ValueError("requiredFeatureCodes values must be unique")
        return self


class DemoEvidenceCandidateCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    selection_policy_version: str = Field(min_length=1)
    baseline_information_coverage_rules: list[BaselineInformationCoverageRule] = Field(
        default_factory=list
    )
    candidates: list[EvidenceCandidateDefinition] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_types(self) -> "DemoEvidenceCandidateCatalogData":
        evidence_types = [item.evidence_type for item in self.candidates]
        if len(evidence_types) != len(set(evidence_types)):
            raise ValueError("candidate evidenceType values must be unique")
        coverage_codes = [
            item.information_content_code for item in self.baseline_information_coverage_rules
        ]
        if len(coverage_codes) != len(set(coverage_codes)):
            raise ValueError("baseline coverage informationContentCode values must be unique")
        return self
