from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType
from app.schemas.data_source import DataSourceState


class AssessmentStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNSUPPORTED_CUSTOMER_TYPE = "UNSUPPORTED_CUSTOMER_TYPE"
    FAILED = "FAILED"


class CalibrationMode(StrEnum):
    RULE_TABLE = "RULE_TABLE"
    CONFORMAL_CALIBRATED = "CONFORMAL_CALIBRATED"


class AssessmentUncertainty(ApiModel):
    point_estimate: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    grade_set: list[str] = Field(default_factory=list)
    calibration_mode: CalibrationMode
    calibration_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_uncertainty(self) -> "AssessmentUncertainty":
        has_lower = self.lower_bound is not None
        has_upper = self.upper_bound is not None
        if has_lower != has_upper:
            raise ValueError("uncertainty interval requires both bounds")
        if has_lower and has_upper:
            if self.lower_bound > self.upper_bound:
                raise ValueError("lowerBound cannot exceed upperBound")
            if self.point_estimate is not None and not (
                self.lower_bound <= self.point_estimate <= self.upper_bound
            ):
                raise ValueError("pointEstimate must be within the uncertainty interval")
        if not has_lower and not self.grade_set:
            raise ValueError("uncertainty requires an interval or gradeSet")
        if any(not grade.strip() for grade in self.grade_set):
            raise ValueError("gradeSet values cannot be blank")
        if len(self.grade_set) != len(set(self.grade_set)):
            raise ValueError("gradeSet values must be unique")
        return self


class AssessmentInputSnapshot(ApiModel):
    session_id: str = Field(min_length=1)
    demo_profile_id: str = Field(min_length=1)
    data_sources: list[DataSourceState]
    demo_only: Literal[True] = True


class AdapterAssessmentResult(ApiModel):
    status: AssessmentStatus
    model_version: str | None = None
    reason_code: str | None = None
    uncertainty: AssessmentUncertainty | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "AdapterAssessmentResult":
        if self.status == AssessmentStatus.NOT_RUN:
            raise ValueError("assessment adapter cannot return NOT_RUN")
        if self.status == AssessmentStatus.COMPLETED:
            if self.model_version is None:
                raise ValueError("COMPLETED assessment requires modelVersion")
            if self.uncertainty is None:
                raise ValueError("COMPLETED assessment requires uncertainty")
        elif not self.reason_code:
            raise ValueError("incomplete assessment requires reasonCode")
        elif self.uncertainty is not None:
            raise ValueError("incomplete assessment cannot expose uncertainty")
        return self


class DemoAssessmentDefinition(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    result: AdapterAssessmentResult


class DemoAssessmentCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    required_verified_sources: list[ConsentSourceType] = Field(min_length=1)
    assessments: list[DemoAssessmentDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_profiles(self) -> "DemoAssessmentCatalogData":
        source_types = self.required_verified_sources
        if len(source_types) != len(set(source_types)):
            raise ValueError("required verified sourceType values must be unique")
        profile_ids = [item.demo_profile_id for item in self.assessments]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("demoProfileId values must be unique")
        return self


class AssessmentState(ApiModel):
    assessment_id: str | None = None
    status: AssessmentStatus
    calculated_at: datetime | None = None
    input_snapshot_id: str | None = None
    model_version: str | None = None
    reason_code: str | None = None
    uncertainty: AssessmentUncertainty | None = None
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_state(self) -> "AssessmentState":
        if self.calculated_at is not None and self.calculated_at.tzinfo is None:
            raise ValueError("calculatedAt must include a timezone")
        execution_fields = (
            self.assessment_id,
            self.calculated_at,
            self.input_snapshot_id,
        )
        if self.status == AssessmentStatus.NOT_RUN:
            if any(value is not None for value in execution_fields):
                raise ValueError("NOT_RUN assessment cannot have execution metadata")
            if self.model_version is not None or self.reason_code is not None:
                raise ValueError("NOT_RUN assessment cannot have a result")
            if self.uncertainty is not None:
                raise ValueError("NOT_RUN assessment cannot have uncertainty")
            return self
        if any(value is None for value in execution_fields):
            raise ValueError("executed assessment requires execution metadata")
        if self.status == AssessmentStatus.COMPLETED:
            if self.model_version is None:
                raise ValueError("COMPLETED assessment requires modelVersion")
            if self.uncertainty is None:
                raise ValueError("COMPLETED assessment requires uncertainty")
        elif not self.reason_code:
            raise ValueError("incomplete assessment requires reasonCode")
        elif self.uncertainty is not None:
            raise ValueError("incomplete assessment cannot expose uncertainty")
        return self


class AssessmentResponse(ApiModel):
    session_id: str = Field(min_length=1)
    assessment: AssessmentState


class SupplementalAssessmentRunRequest(ApiModel):
    submission_id: str = Field(min_length=1)


class AcceptedEvidenceSnapshot(ApiModel):
    quality_check_id: str = Field(min_length=1)
    submission_id: str = Field(min_length=1)
    selection_id: str = Field(min_length=1)
    boundary_check_id: str = Field(min_length=1)
    resolution_id: str | None = Field(default=None, min_length=1)
    evidence_type: str = Field(min_length=1)
    source_type: ConsentSourceType
    observed_at: datetime
    checked_at: datetime
    submission_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_data_version: str = Field(min_length=1)
    quality_policy_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_evidence_timestamps(self) -> "AcceptedEvidenceSnapshot":
        if self.observed_at.tzinfo is None or self.checked_at.tzinfo is None:
            raise ValueError("accepted Evidence timestamps must include a timezone")
        return self


class SupplementalAssessmentInputSnapshot(ApiModel):
    session_id: str = Field(min_length=1)
    demo_profile_id: str = Field(min_length=1)
    baseline_assessment_id: str = Field(min_length=1)
    baseline_input_snapshot_id: str = Field(min_length=1)
    baseline_uncertainty: AssessmentUncertainty
    data_sources: list[DataSourceState]
    accepted_evidence: AcceptedEvidenceSnapshot
    accepted_evidence_set: list[AcceptedEvidenceSnapshot] = Field(default_factory=list)
    demo_only: Literal[True] = True

    @model_validator(mode="before")
    @classmethod
    def restore_legacy_evidence_set(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "acceptedEvidenceSet" in data or "accepted_evidence_set" in data:
            return data
        accepted_evidence = data.get("acceptedEvidence", data.get("accepted_evidence"))
        if accepted_evidence is None:
            return data
        restored = dict(data)
        restored["acceptedEvidenceSet"] = [accepted_evidence]
        return restored

    @model_validator(mode="after")
    def validate_accepted_evidence_set(self) -> "SupplementalAssessmentInputSnapshot":
        if not self.accepted_evidence_set:
            raise ValueError("acceptedEvidenceSet cannot be empty")
        if self.accepted_evidence_set[-1] != self.accepted_evidence:
            raise ValueError("acceptedEvidence must be the latest acceptedEvidenceSet item")
        submission_ids = [item.submission_id for item in self.accepted_evidence_set]
        quality_check_ids = [item.quality_check_id for item in self.accepted_evidence_set]
        evidence_types = [item.evidence_type for item in self.accepted_evidence_set]
        if len(submission_ids) != len(set(submission_ids)):
            raise ValueError("acceptedEvidenceSet submissionId values must be unique")
        if len(quality_check_ids) != len(set(quality_check_ids)):
            raise ValueError("acceptedEvidenceSet qualityCheckId values must be unique")
        if len(evidence_types) != len(set(evidence_types)):
            raise ValueError("acceptedEvidenceSet evidenceType values must be unique")
        return self


class SupplementalAssessmentState(ApiModel):
    supplemental_assessment_id: str = Field(min_length=1)
    baseline_assessment_id: str = Field(min_length=1)
    quality_check_id: str = Field(min_length=1)
    submission_id: str = Field(min_length=1)
    status: AssessmentStatus
    calculated_at: datetime
    input_snapshot_id: str = Field(min_length=1)
    model_version: str | None = None
    reason_code: str | None = None
    uncertainty: AssessmentUncertainty | None = None
    accepted_evidence_count: int = Field(default=1, ge=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_supplemental_state(self) -> "SupplementalAssessmentState":
        if self.calculated_at.tzinfo is None:
            raise ValueError("calculatedAt must include a timezone")
        if self.status == AssessmentStatus.NOT_RUN:
            raise ValueError("saved supplemental assessment cannot be NOT_RUN")
        if self.status == AssessmentStatus.COMPLETED:
            if self.model_version is None:
                raise ValueError("COMPLETED supplemental assessment requires modelVersion")
            if self.uncertainty is None:
                raise ValueError("COMPLETED supplemental assessment requires uncertainty")
        elif not self.reason_code:
            raise ValueError("incomplete supplemental assessment requires reasonCode")
        elif self.uncertainty is not None:
            raise ValueError("incomplete supplemental assessment cannot expose uncertainty")
        return self


class SupplementalAssessmentResponse(ApiModel):
    session_id: str = Field(min_length=1)
    supplemental_assessment: SupplementalAssessmentState | None


class AssessmentComparisonBasis(StrEnum):
    GRADE_SET = "GRADE_SET"
    NUMERIC_INTERVAL = "NUMERIC_INTERVAL"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class AssessmentUncertaintyChange(StrEnum):
    NARROWED = "NARROWED"
    UNCHANGED = "UNCHANGED"
    EXPANDED = "EXPANDED"
    SHIFTED = "SHIFTED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class AssessmentComparisonState(ApiModel):
    comparison_id: str = Field(min_length=1)
    baseline_assessment_id: str = Field(min_length=1)
    supplemental_assessment_id: str = Field(min_length=1)
    quality_check_id: str = Field(min_length=1)
    basis: AssessmentComparisonBasis
    uncertainty_change: AssessmentUncertaintyChange
    before_uncertainty: AssessmentUncertainty | None
    after_uncertainty: AssessmentUncertainty | None
    rationale_codes: list[str] = Field(min_length=1)
    baseline_model_version: str | None
    supplemental_model_version: str | None
    compared_at: datetime
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_comparison(self) -> "AssessmentComparisonState":
        if self.compared_at.tzinfo is None:
            raise ValueError("comparedAt must include a timezone")
        if len(self.rationale_codes) != len(set(self.rationale_codes)):
            raise ValueError("rationaleCodes values must be unique")
        is_not_comparable = self.basis == AssessmentComparisonBasis.NOT_COMPARABLE
        if is_not_comparable != (
            self.uncertainty_change == AssessmentUncertaintyChange.NOT_COMPARABLE
        ):
            raise ValueError("comparison basis and uncertainty change must agree")
        return self


class AssessmentComparisonResponse(ApiModel):
    session_id: str = Field(min_length=1)
    comparison: AssessmentComparisonState | None


class DemoSupplementalAssessmentDefinition(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    evidence_type: str | None = Field(default=None, min_length=1)
    evidence_types: list[str] = Field(default_factory=list)
    result: AdapterAssessmentResult

    @model_validator(mode="after")
    def validate_evidence_input(self) -> "DemoSupplementalAssessmentDefinition":
        if self.evidence_type is None and not self.evidence_types:
            raise ValueError("supplemental assessment requires Evidence input")
        if self.evidence_type is not None and self.evidence_types:
            raise ValueError("use either evidenceType or evidenceTypes")
        if len(self.evidence_types) != len(set(self.evidence_types)):
            raise ValueError("evidenceTypes values must be unique")
        if any(not evidence_type.strip() for evidence_type in self.evidence_types):
            raise ValueError("evidenceTypes values cannot be blank")
        return self

    def evidence_type_key(self) -> tuple[str, ...]:
        values = self.evidence_types or [self.evidence_type]
        return tuple(sorted(value for value in values if value is not None))


class DemoSupplementalAssessmentCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    assessments: list[DemoSupplementalAssessmentDefinition] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_inputs(self) -> "DemoSupplementalAssessmentCatalogData":
        inputs = [(item.demo_profile_id, item.evidence_type_key()) for item in self.assessments]
        if len(inputs) != len(set(inputs)):
            raise ValueError("supplemental assessment input pairs must be unique")
        return self
