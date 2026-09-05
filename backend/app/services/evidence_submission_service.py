import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import ResourceConflictError
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.evidence_selection import EvidenceSelectionStatus
from app.schemas.evidence_submission import (
    DemoEvidenceSubmissionCatalogData,
    DemoEvidenceSubmissionDefinition,
    EvidenceSubmissionCreateRequest,
    EvidenceSubmissionResponse,
    EvidenceSubmissionState,
    EvidenceSubmissionStatus,
)
from app.services.evidence_selection_service import EvidenceSelectionService
from app.services.session_service import CustomerSessionService


class DemoEvidenceSubmissionCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoEvidenceSubmissionCatalogData | None = None
        self._submissions: dict[str, DemoEvidenceSubmissionDefinition] = {}

    def get(self, evidence_type: str) -> DemoEvidenceSubmissionDefinition | None:
        self._load()
        return self._submissions.get(evidence_type)

    def is_ready(self) -> bool:
        try:
            self._load()
        except (OSError, ValueError):
            return False
        return True

    def _load(self) -> DemoEvidenceSubmissionCatalogData:
        if self._catalog is None:
            self._catalog = DemoEvidenceSubmissionCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
            self._submissions = {item.evidence_type: item for item in self._catalog.submissions}
        return self._catalog


class EvidenceSubmissionService:
    def __init__(
        self,
        repository: EvidenceSubmissionRepository,
        session_service: CustomerSessionService,
        selection_service: EvidenceSelectionService,
        catalog: DemoEvidenceSubmissionCatalog,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.selection_service = selection_service
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> EvidenceSubmissionResponse:
        self.session_service.get_session(session_id)
        return EvidenceSubmissionResponse(
            session_id=session_id,
            submission=self.repository.get_latest(session_id),
        )

    def submit_demo(
        self,
        session_id: str,
        payload: EvidenceSubmissionCreateRequest,
        request_id: str,
    ) -> EvidenceSubmissionResponse:
        self.session_service.get_session(session_id)
        selection = self.selection_service.get_latest(session_id).selection
        if selection is None or selection.selection_id != payload.selection_id:
            raise ResourceConflictError(
                code="EVIDENCE_SELECTION_NOT_READY",
                message="현재 세션의 최신 Evidence 선택 결과가 필요합니다.",
            )
        if (
            selection.status != EvidenceSelectionStatus.SELECTED
            or selection.selected_evidence is None
        ):
            raise ResourceConflictError(
                code="EVIDENCE_NOT_SELECTED",
                message="제출할 Evidence가 선택되지 않았습니다.",
            )

        existing = self.repository.get_by_selection_id(selection.selection_id)
        if existing is not None:
            return EvidenceSubmissionResponse(session_id=session_id, submission=existing)

        definition = self.catalog.get(selection.selected_evidence.evidence_type)
        if definition is None:
            raise ResourceConflictError(
                code="DEMO_EVIDENCE_SUBMISSION_NOT_CONFIGURED",
                message="선택된 Evidence의 Demo 제출 자료가 구성되지 않았습니다.",
            )

        submitted_at = datetime.now(UTC)
        snapshot = {
            "selectionId": selection.selection_id,
            "evidenceType": selection.selected_evidence.evidence_type,
            "sourceType": selection.selected_evidence.source_type.value,
            "submissionMode": payload.submission_mode,
            "observedAt": definition.observed_at.isoformat(),
            "sourceReference": definition.source_reference,
            "dataVersion": definition.data_version,
        }
        serialized = json.dumps(
            snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_hash = hashlib.sha256(serialized.encode()).hexdigest()
        state = EvidenceSubmissionState(
            submission_id=f"evd_{uuid4().hex}",
            selection_id=selection.selection_id,
            evidence_type=selection.selected_evidence.evidence_type,
            source_type=selection.selected_evidence.source_type,
            submission_mode=payload.submission_mode,
            status=EvidenceSubmissionStatus.RECEIVED,
            submitted_at=submitted_at,
            observed_at=definition.observed_at,
            submission_snapshot_hash=snapshot_hash,
            data_version=definition.data_version,
        )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.EVIDENCE_SUBMITTED,
            timestamp=submitted_at,
            actor=AuditActor.SYSTEM,
            input_version=selection.selection_id,
            input_snapshot_hash=snapshot_hash,
            output_summary={
                "submissionStatus": state.status.value,
                "evidenceType": state.evidence_type,
                "sourceType": state.source_type.value,
                "submissionMode": state.submission_mode.value,
                "demoOnly": state.demo_only,
            },
            data_version=state.data_version,
            policy_version=selection.selection_policy_version,
        )
        saved = self.repository.save_submission(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return EvidenceSubmissionResponse(session_id=session_id, submission=saved)

    def readiness(self) -> dict[str, bool]:
        return {
            "evidence_submission_repository": self.repository.is_ready(),
            "evidence_submission_catalog": self.catalog.is_ready(),
        }
