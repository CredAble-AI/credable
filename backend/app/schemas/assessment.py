from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.data_source import DataSourceState


class AssessmentStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNSUPPORTED_CUSTOMER_TYPE = "UNSUPPORTED_CUSTOMER_TYPE"
    FAILED = "FAILED"


class AssessmentInputSnapshot(ApiModel):
    session_id: str = Field(min_length=1)
    demo_profile_id: str = Field(min_length=1)
    data_sources: list[DataSourceState]
    demo_only: Literal[True] = True


class AdapterAssessmentResult(ApiModel):
    status: AssessmentStatus
    model_version: str | None = None
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "AdapterAssessmentResult":
        if self.status == AssessmentStatus.NOT_RUN:
            raise ValueError("assessment adapter cannot return NOT_RUN")
        if self.status == AssessmentStatus.COMPLETED:
            if self.model_version is None:
                raise ValueError("COMPLETED assessment requires modelVersion")
        elif not self.reason_code:
            raise ValueError("incomplete assessment requires reasonCode")
        return self


class AssessmentState(ApiModel):
    assessment_id: str | None = None
    status: AssessmentStatus
    calculated_at: datetime | None = None
    input_snapshot_id: str | None = None
    model_version: str | None = None
    reason_code: str | None = None
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
            return self
        if any(value is None for value in execution_fields):
            raise ValueError("executed assessment requires execution metadata")
        if self.status == AssessmentStatus.COMPLETED:
            if self.model_version is None:
                raise ValueError("COMPLETED assessment requires modelVersion")
        elif not self.reason_code:
            raise ValueError("incomplete assessment requires reasonCode")
        return self


class AssessmentResponse(ApiModel):
    session_id: str = Field(min_length=1)
    assessment: AssessmentState
