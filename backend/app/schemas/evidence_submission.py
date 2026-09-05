from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType
from app.schemas.evidence_file import UploadedEvidenceFile


class EvidenceSubmissionMode(StrEnum):
    DEMO_FIXTURE_REFERENCE = "DEMO_FIXTURE_REFERENCE"
    DEMO_FILE_UPLOAD = "DEMO_FILE_UPLOAD"


class EvidenceSubmissionStatus(StrEnum):
    RECEIVED = "RECEIVED"


class EvidenceSubmissionCreateRequest(ApiModel):
    selection_id: str = Field(min_length=1)
    submission_mode: Literal[EvidenceSubmissionMode.DEMO_FIXTURE_REFERENCE]


class EvidenceSubmissionState(ApiModel):
    submission_id: str = Field(min_length=1)
    selection_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    source_type: ConsentSourceType
    submission_mode: EvidenceSubmissionMode
    status: EvidenceSubmissionStatus
    submitted_at: datetime
    observed_at: datetime
    submission_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_version: str = Field(min_length=1)
    uploaded_file: UploadedEvidenceFile | None = None
    evidence_consent_id: str | None = Field(default=None, min_length=1)
    consent_scope_version: str | None = Field(default=None, min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_timestamps(self) -> "EvidenceSubmissionState":
        if self.submitted_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("submission timestamps must include a timezone")
        if self.observed_at > self.submitted_at:
            raise ValueError("observedAt cannot be later than submittedAt")
        return self


class EvidenceSubmissionResponse(ApiModel):
    session_id: str = Field(min_length=1)
    submission: EvidenceSubmissionState | None


class DemoEvidenceSubmissionDefinition(ApiModel):
    evidence_type: str = Field(min_length=1)
    observed_at: datetime
    source_reference: str = Field(min_length=1)
    data_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_observed_at(self) -> "DemoEvidenceSubmissionDefinition":
        if self.observed_at.tzinfo is None:
            raise ValueError("observedAt must include a timezone")
        return self


class DemoEvidenceSubmissionCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    submissions: list[DemoEvidenceSubmissionDefinition] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_types(self) -> "DemoEvidenceSubmissionCatalogData":
        evidence_types = [item.evidence_type for item in self.submissions]
        if len(evidence_types) != len(set(evidence_types)):
            raise ValueError("submission evidenceType values must be unique")
        return self
