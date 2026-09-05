from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import EvidenceSubmissionNotFoundError
from app.repositories.evidence_quality_repository import EvidenceQualityRepository
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.evidence_quality import (
    DemoEvidenceQualityCatalogData,
    DemoEvidenceQualityDefinition,
    EvidenceQualityDimension,
    EvidenceQualityDimensionResult,
    EvidenceQualityDimensionStatus,
    EvidenceQualityResponse,
    EvidenceQualityState,
    EvidenceQualityStatus,
)
from app.schemas.evidence_submission import EvidenceSubmissionState
from app.services.session_service import CustomerSessionService


class DemoEvidenceQualityCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoEvidenceQualityCatalogData | None = None
        self._results: dict[str, DemoEvidenceQualityDefinition] = {}

    @property
    def quality_policy_version(self) -> str:
        return self._load().quality_policy_version

    def get(self, evidence_type: str) -> DemoEvidenceQualityDefinition | None:
        self._load()
        return self._results.get(evidence_type)

    def is_ready(self) -> bool:
        try:
            self._load()
        except (OSError, ValueError):
            return False
        return True

    def _load(self) -> DemoEvidenceQualityCatalogData:
        if self._catalog is None:
            self._catalog = DemoEvidenceQualityCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
            self._results = {item.evidence_type: item for item in self._catalog.results}
        return self._catalog


class EvidenceQualityService:
    def __init__(
        self,
        repository: EvidenceQualityRepository,
        submission_repository: EvidenceSubmissionRepository,
        session_service: CustomerSessionService,
        catalog: DemoEvidenceQualityCatalog,
    ) -> None:
        self.repository = repository
        self.submission_repository = submission_repository
        self.session_service = session_service
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()

    def get(
        self,
        session_id: str,
        submission_id: str,
    ) -> EvidenceQualityResponse:
        submission = self._submission(session_id, submission_id)
        return EvidenceQualityResponse(
            session_id=session_id,
            quality=self.repository.get_for_submission(session_id, submission.submission_id),
        )

    def check(
        self,
        session_id: str,
        submission_id: str,
        request_id: str,
    ) -> EvidenceQualityResponse:
        submission = self._submission(session_id, submission_id)
        existing = self.repository.get_for_submission(session_id, submission_id)
        if existing is not None:
            return EvidenceQualityResponse(session_id=session_id, quality=existing)

        definition = self.catalog.get(submission.evidence_type)
        checks = (
            definition.checks
            if definition is not None
            else [
                EvidenceQualityDimensionResult(
                    dimension=dimension,
                    status=EvidenceQualityDimensionStatus.NOT_VERIFIED,
                    rationale_code=f"DEMO_{dimension.value}_POLICY_NOT_CONFIGURED",
                )
                for dimension in EvidenceQualityDimension
            ]
        )
        rejection_codes = [
            item.rationale_code
            for item in checks
            if item.status != EvidenceQualityDimensionStatus.PASSED
        ]
        status = (
            EvidenceQualityStatus.REJECTED if rejection_codes else EvidenceQualityStatus.ACCEPTED
        )
        checked_at = datetime.now(UTC)
        state = EvidenceQualityState(
            quality_check_id=f"evq_{uuid4().hex}",
            submission_id=submission.submission_id,
            evidence_type=submission.evidence_type,
            status=status,
            checks=checks,
            rejection_codes=rejection_codes,
            eligible_for_reassessment=status == EvidenceQualityStatus.ACCEPTED,
            checked_at=checked_at,
            submission_snapshot_hash=submission.submission_snapshot_hash,
            data_version=submission.data_version,
            quality_policy_version=self.catalog.quality_policy_version,
        )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.EVIDENCE_QUALITY_CHECKED,
            timestamp=checked_at,
            actor=AuditActor.SYSTEM,
            input_version=submission.submission_id,
            input_snapshot_hash=submission.submission_snapshot_hash,
            output_summary={
                "qualityStatus": state.status.value,
                "failedCheckCount": len(rejection_codes),
                "eligibleForReassessment": state.eligible_for_reassessment,
                "evidenceType": state.evidence_type,
                "demoOnly": state.demo_only,
            },
            data_version=state.data_version,
            policy_version=state.quality_policy_version,
        )
        saved = self.repository.save_quality(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return EvidenceQualityResponse(session_id=session_id, quality=saved)

    def _submission(
        self,
        session_id: str,
        submission_id: str,
    ) -> EvidenceSubmissionState:
        self.session_service.get_session(session_id)
        submission = self.submission_repository.get_for_session(session_id, submission_id)
        if submission is None:
            raise EvidenceSubmissionNotFoundError(submission_id)
        return submission

    def readiness(self) -> dict[str, bool]:
        return {
            "evidence_quality_repository": self.repository.is_ready(),
            "evidence_quality_catalog": self.catalog.is_ready(),
        }
