from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class ExplanationTargetType(StrEnum):
    BASELINE_ASSESSMENT = "BASELINE_ASSESSMENT"
    SUPPLEMENTAL_ASSESSMENT = "SUPPLEMENTAL_ASSESSMENT"


class ExplanationSourceType(StrEnum):
    BASELINE_ASSESSMENT = "BASELINE_ASSESSMENT"
    POLICY_BOUNDARY = "POLICY_BOUNDARY"
    SUPPLEMENTAL_ASSESSMENT = "SUPPLEMENTAL_ASSESSMENT"
    ASSESSMENT_COMPARISON = "ASSESSMENT_COMPARISON"
    EVIDENCE_RESOLUTION = "EVIDENCE_RESOLUTION"


class ExplanationRenderingMode(StrEnum):
    DEMO_TEMPLATE = "DEMO_TEMPLATE"
    GENERATIVE_AI = "GENERATIVE_AI"
    RULE_FALLBACK = "RULE_FALLBACK"


class ExplanationFact(ApiModel):
    fact_code: str = Field(min_length=1)
    source_reference_id: str = Field(min_length=1)
    values: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_values(self) -> "ExplanationFact":
        if any(not value.strip() for value in self.values):
            raise ValueError("explanation fact values cannot be blank")
        if len(self.values) != len(set(self.values)):
            raise ValueError("explanation fact values must be unique")
        return self


class ExplanationSourceReference(ApiModel):
    source_type: ExplanationSourceType
    source_id: str = Field(min_length=1)
    data_version: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    policy_version: str | None = Field(default=None, min_length=1)


class AssessmentExplanationInputSnapshot(ApiModel):
    session_id: str = Field(min_length=1)
    target_type: ExplanationTargetType
    target_assessment_id: str = Field(min_length=1)
    facts: list[ExplanationFact] = Field(min_length=1)
    source_references: list[ExplanationSourceReference] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_snapshot(self) -> "AssessmentExplanationInputSnapshot":
        fact_codes = [fact.fact_code for fact in self.facts]
        if len(fact_codes) != len(set(fact_codes)):
            raise ValueError("explanation factCode values must be unique")
        source_ids = [source.source_id for source in self.source_references]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("explanation sourceId values must be unique")
        known_sources = set(source_ids)
        if self.target_assessment_id not in known_sources:
            raise ValueError("targetAssessmentId must exist in sourceReferences")
        if any(fact.source_reference_id not in known_sources for fact in self.facts):
            raise ValueError("explanation facts must reference known sources")
        return self


class ExplanationPlan(ApiModel):
    headline_code: str = Field(min_length=1)
    section_codes: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_codes(self) -> "ExplanationPlan":
        if len(self.section_codes) != len(set(self.section_codes)):
            raise ValueError("explanation sectionCodes must be unique")
        if self.headline_code not in self.section_codes:
            raise ValueError("headlineCode must exist in sectionCodes")
        return self


class ExplanationSection(ApiModel):
    message_code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_reference_ids: list[str] = Field(min_length=1)


class AssessmentExplanationState(ApiModel):
    explanation_id: str = Field(min_length=1)
    target_type: ExplanationTargetType
    target_assessment_id: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    sections: list[ExplanationSection] = Field(min_length=1, max_length=8)
    caution_text: str = Field(min_length=1)
    source_references: list[ExplanationSourceReference] = Field(min_length=1)
    input_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rendering_mode: ExplanationRenderingMode
    fallback_applied: bool
    fallback_reason_code: str | None = Field(default=None, min_length=1)
    provider_version: str = Field(min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    prompt_version: str = Field(min_length=1)
    explanation_policy_version: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    generated_at: datetime
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_state(self) -> "AssessmentExplanationState":
        if self.generated_at.tzinfo is None:
            raise ValueError("generatedAt must include a timezone")
        is_fallback = self.rendering_mode == ExplanationRenderingMode.RULE_FALLBACK
        if self.fallback_applied != is_fallback:
            raise ValueError("fallbackApplied must match renderingMode")
        if is_fallback != (self.fallback_reason_code is not None):
            raise ValueError("fallbackReasonCode must exist only for fallback output")
        if self.rendering_mode == ExplanationRenderingMode.GENERATIVE_AI:
            if self.model_version is None:
                raise ValueError("GENERATIVE_AI output requires modelVersion")
        elif self.model_version is not None:
            raise ValueError("non-generative output cannot expose modelVersion")
        source_ids = {source.source_id for source in self.source_references}
        if self.target_assessment_id not in source_ids:
            raise ValueError("targetAssessmentId must exist in sourceReferences")
        section_codes = [section.message_code for section in self.sections]
        if len(section_codes) != len(set(section_codes)):
            raise ValueError("explanation messageCode values must be unique")
        if any(
            not set(section.source_reference_ids).issubset(source_ids) for section in self.sections
        ):
            raise ValueError("explanation sections must reference known sources")
        return self


class AssessmentExplanationResponse(ApiModel):
    session_id: str = Field(min_length=1)
    explanation: AssessmentExplanationState | None
