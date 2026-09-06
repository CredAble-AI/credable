from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.assessment import (
    AdapterAssessmentResult,
    AssessmentInputSnapshot,
    AssessmentStatus,
    DemoAssessmentCatalogData,
    DemoSupplementalAssessmentCatalogData,
    SupplementalAssessmentInputSnapshot,
)
from app.schemas.data_source import RetrievalStatus, VerificationStatus


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


class DemoAssessmentAdapter(AssessmentAdapter):
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoAssessmentCatalogData | None = None
        self._results: dict[str, AdapterAssessmentResult] = {}

    def run(self, snapshot: AssessmentInputSnapshot) -> AdapterAssessmentResult:
        self._initialize()
        if self._catalog is None:
            raise RuntimeError("Demo assessment catalog is not initialized")
        sources = {item.source_type: item for item in snapshot.data_sources}
        required_sources_ready = all(
            source_type in sources
            and sources[source_type].retrieval_status == RetrievalStatus.RETRIEVED
            and sources[source_type].verification_status == VerificationStatus.VERIFIED
            for source_type in self._catalog.required_verified_sources
        )
        if not required_sources_ready:
            return AdapterAssessmentResult(
                status=AssessmentStatus.INSUFFICIENT_DATA,
                reason_code="DEMO_REQUIRED_DATA_NOT_VERIFIED",
            )
        if snapshot.feature_cutoff_at is not None:
            eligible_source_types = {item.source_type for item in snapshot.source_snapshots}
            required_source_after_cutoff = any(
                item.source_type in self._catalog.required_verified_sources
                for item in snapshot.excluded_source_snapshots
            )
            if required_source_after_cutoff:
                return AdapterAssessmentResult(
                    status=AssessmentStatus.INSUFFICIENT_DATA,
                    reason_code="DEMO_REQUIRED_DATA_AFTER_FEATURE_CUTOFF",
                )
            if any(
                source_type not in eligible_source_types
                for source_type in self._catalog.required_verified_sources
            ):
                return AdapterAssessmentResult(
                    status=AssessmentStatus.INSUFFICIENT_DATA,
                    reason_code="DEMO_REQUIRED_DATA_SNAPSHOT_NOT_AVAILABLE",
                )
        if snapshot.source_assessment is None:
            return AdapterAssessmentResult(
                status=AssessmentStatus.INSUFFICIENT_DATA,
                reason_code="EXISTING_BANK_ASSESSMENT_NOT_AVAILABLE",
            )
        return self._results.get(
            snapshot.source_assessment.credit_assessment_id,
            AdapterAssessmentResult(
                status=AssessmentStatus.MODEL_NOT_CONFIGURED,
                reason_code="DEMO_SOURCE_ASSESSMENT_NOT_CONFIGURED",
            ),
        )

    def is_ready(self) -> bool:
        try:
            self._initialize()
        except (OSError, ValueError):
            return False
        return True

    def _initialize(self) -> None:
        if self._catalog is not None:
            return
        catalog = DemoAssessmentCatalogData.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self._catalog = catalog
        self._results = {
            item.source_credit_assessment_id: item.result for item in catalog.assessments
        }


class SupplementalAssessmentAdapter(ABC):
    @abstractmethod
    def run(self, snapshot: SupplementalAssessmentInputSnapshot) -> AdapterAssessmentResult:
        """Run an approved supplemental model using accepted Evidence metadata."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the adapter can return an explicit execution state."""


class UnconfiguredSupplementalAssessmentAdapter(SupplementalAssessmentAdapter):
    def run(self, snapshot: SupplementalAssessmentInputSnapshot) -> AdapterAssessmentResult:
        del snapshot
        return AdapterAssessmentResult(
            status=AssessmentStatus.MODEL_NOT_CONFIGURED,
            reason_code="DEMO_SUPPLEMENTAL_ASSESSMENT_MODEL_NOT_CONFIGURED",
        )

    def is_ready(self) -> bool:
        return True


class DemoSupplementalAssessmentAdapter(SupplementalAssessmentAdapter):
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoSupplementalAssessmentCatalogData | None = None
        self._results: dict[tuple[str, tuple[str, ...]], AdapterAssessmentResult] = {}

    def run(self, snapshot: SupplementalAssessmentInputSnapshot) -> AdapterAssessmentResult:
        self._initialize()
        return self._results.get(
            (
                snapshot.demo_profile_id,
                tuple(sorted(item.evidence_type for item in snapshot.accepted_evidence_set)),
            ),
            AdapterAssessmentResult(
                status=AssessmentStatus.MODEL_NOT_CONFIGURED,
                reason_code="DEMO_SUPPLEMENTAL_ASSESSMENT_INPUT_NOT_CONFIGURED",
            ),
        )

    def is_ready(self) -> bool:
        try:
            self._initialize()
        except (OSError, ValueError):
            return False
        return True

    def _initialize(self) -> None:
        if self._catalog is not None:
            return
        catalog = DemoSupplementalAssessmentCatalogData.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self._catalog = catalog
        self._results = {
            (item.demo_profile_id, item.evidence_type_key()): item.result
            for item in catalog.assessments
        }
