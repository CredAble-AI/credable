from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType
from app.schemas.evidence_trust import DemoManifestSignature


class EvidenceCollectionMode(StrEnum):
    DEMO_FILE_UPLOAD = "DEMO_FILE_UPLOAD"
    DEMO_CONNECTION = "DEMO_CONNECTION"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceSubmissionRequirementStatus(StrEnum):
    READY = "READY"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceSubmissionRequirement(ApiModel):
    status: EvidenceSubmissionRequirementStatus
    reason_code: str | None = Field(default=None, min_length=1)
    consent_source_type: ConsentSourceType


class DemoEvidenceFileDescriptor(ApiModel):
    demo_file_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    content_type: Literal["application/pdf"] = "application/pdf"
    size_bytes: int = Field(gt=0)
    download_url: str = Field(min_length=1)
    scenario_code: str = Field(min_length=1)
    expected_quality_status: Literal["ACCEPTED", "REJECTED", "REVIEW_REQUIRED"]


class EvidenceUploadPolicy(ApiModel):
    allowed_content_types: tuple[Literal["application/pdf"], ...] = ("application/pdf",)
    allowed_extensions: tuple[Literal[".pdf"], ...] = (".pdf",)
    max_size_bytes: int = Field(default=5 * 1024 * 1024, gt=0)


class EvidenceSubmissionOptionResponse(ApiModel):
    session_id: str = Field(min_length=1)
    selection_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    collection_mode: EvidenceCollectionMode
    submission_requirement: EvidenceSubmissionRequirement
    demo_file: DemoEvidenceFileDescriptor | None = None
    demo_files: list[DemoEvidenceFileDescriptor] = Field(default_factory=list)
    upload_policy: EvidenceUploadPolicy | None = None
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_file_upload_option(self) -> "EvidenceSubmissionOptionResponse":
        is_file_upload = self.collection_mode == EvidenceCollectionMode.DEMO_FILE_UPLOAD
        if is_file_upload != (self.demo_file is not None and self.upload_policy is not None):
            raise ValueError("DEMO_FILE_UPLOAD requires demoFile and uploadPolicy")
        if is_file_upload and not self.demo_files:
            raise ValueError("DEMO_FILE_UPLOAD requires at least one demoFiles item")
        return self


class UploadedEvidenceFile(ApiModel):
    demo_file_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    content_type: Literal["application/pdf"] = "application/pdf"
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DemoRevenueMonthSummary(ApiModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    sales_amount: int = Field(ge=0)
    deposit_amount: int = Field(ge=0)
    difference_amount: int


class DemoRevenueSummaryTotals(ApiModel):
    sales_amount: int = Field(ge=0)
    deposit_amount: int = Field(ge=0)
    difference_amount: int


class DemoRevenueSummaryManifest(ApiModel):
    business_name: str | None = Field(default=None, min_length=1)
    period_start: date | None = None
    period_end: date | None = None
    generated_on: date | None = None
    demo_notice: str | None = Field(default=None, min_length=1)
    monthly_summaries: list[DemoRevenueMonthSummary] = Field(default_factory=list)
    totals: DemoRevenueSummaryTotals | None = None


class DemoEvidenceFileDefinition(ApiModel):
    demo_file_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    source_type: ConsentSourceType
    collection_mode: Literal[EvidenceCollectionMode.DEMO_FILE_UPLOAD]
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    content_type: Literal["application/pdf"] = "application/pdf"
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trusted_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    scenario_code: str = Field(min_length=1)
    expected_quality_status: Literal["ACCEPTED", "REJECTED", "REVIEW_REQUIRED"]
    is_default: bool = False
    observed_at: datetime
    quality_reference_at: datetime
    data_version: str = Field(min_length=1)
    quality_policy_version: str = Field(min_length=1)
    manifest_signature: DemoManifestSignature | None = None
    required_manifest_fields: list[str] = Field(min_length=1)
    manifest: DemoRevenueSummaryManifest
    upload_policy: EvidenceUploadPolicy = Field(default_factory=EvidenceUploadPolicy)

    @model_validator(mode="after")
    def validate_definition(self) -> "DemoEvidenceFileDefinition":
        if self.observed_at.tzinfo is None or self.quality_reference_at.tzinfo is None:
            raise ValueError("Demo file timestamps must include a timezone")
        if len(self.required_manifest_fields) != len(set(self.required_manifest_fields)):
            raise ValueError("requiredManifestFields values must be unique")
        if self.is_default and self.expected_quality_status != "ACCEPTED":
            raise ValueError("The default Demo file must be an ACCEPTED scenario")
        return self


class DemoEvidenceFileCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    files: list[DemoEvidenceFileDefinition] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_files(self) -> "DemoEvidenceFileCatalogData":
        file_ids = [item.demo_file_id for item in self.files]
        hashes = [item.sha256 for item in self.files]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError("demoFileId values must be unique")
        if len(hashes) != len(set(hashes)):
            raise ValueError("Demo file sha256 values must be unique")
        evidence_types = {item.evidence_type for item in self.files}
        for evidence_type in evidence_types:
            defaults = [
                item
                for item in self.files
                if item.evidence_type == evidence_type and item.is_default
            ]
            if len(defaults) != 1:
                raise ValueError("Each Demo file evidenceType requires exactly one default file")
        return self
