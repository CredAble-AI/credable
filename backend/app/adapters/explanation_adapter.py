from abc import ABC, abstractmethod

from app.schemas.explanation import (
    AssessmentExplanationInputSnapshot,
    ExplanationPlan,
    ExplanationRenderingMode,
)


class ExplanationProvider(ABC):
    provider_version: str
    rendering_mode: ExplanationRenderingMode
    model_version: str | None
    prompt_version: str

    @abstractmethod
    def plan(
        self,
        snapshot: AssessmentExplanationInputSnapshot,
        allowed_message_codes: tuple[str, ...],
    ) -> ExplanationPlan:
        """Select only message codes allowed by the server-owned fact policy."""


class DemoExplanationProvider(ExplanationProvider):
    provider_version = "demo-explanation-provider-v1"
    rendering_mode = ExplanationRenderingMode.DEMO_TEMPLATE
    model_version = None
    prompt_version = "explanation-message-plan-v1"

    def plan(
        self,
        snapshot: AssessmentExplanationInputSnapshot,
        allowed_message_codes: tuple[str, ...],
    ) -> ExplanationPlan:
        del snapshot
        selected = list(allowed_message_codes[-8:])
        return ExplanationPlan(
            headline_code=selected[-1],
            section_codes=selected,
        )
