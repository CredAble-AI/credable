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
