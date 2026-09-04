from abc import ABC, abstractmethod

from app.schemas.assessment import (
    AdapterAssessmentResult,
    AssessmentInputSnapshot,
    AssessmentStatus,
)


class AssessmentAdapter(ABC):
    @abstractmethod
    def run(self, snapshot: AssessmentInputSnapshot) -> AdapterAssessmentResult:
        """Run an approved model without exposing implementation details."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the adapter can return an explicit execution state."""


class UnconfiguredDemoAssessmentAdapter(AssessmentAdapter):
    """Avoids generating a score until a Demo model is explicitly configured."""

    def run(self, snapshot: AssessmentInputSnapshot) -> AdapterAssessmentResult:
        del snapshot
        return AdapterAssessmentResult(
            status=AssessmentStatus.MODEL_NOT_CONFIGURED,
            reason_code="DEMO_ASSESSMENT_MODEL_NOT_CONFIGURED",
        )

    def is_ready(self) -> bool:
        return True
