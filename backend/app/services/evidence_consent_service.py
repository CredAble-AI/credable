import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.repositories.evidence_consent_repository import EvidenceConsentRepository
from app.repositories.evidence_selection_repository import EvidenceSelectionRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.consent import ConsentStatus
from app.schemas.evidence_consent import EvidenceConsentResponse, EvidenceConsentState
from app.schemas.evidence_selection import EvidenceSelectionState, EvidenceSelectionStatus
from app.services.session_service import CustomerSessionService


class EvidenceConsentService:
    def __init__(
        self,
        repository: EvidenceConsentRepository,
        session_service: CustomerSessionService,
        selection_repository: EvidenceSelectionRepository,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.selection_repository = selection_repository

    def initialize(self) -> None:
        self.repository.initialize()

    def get(self, session_id: str, selection_id: str) -> EvidenceConsentResponse:
        selection = self._require_current_selection(session_id, selection_id)
        pending = self._pending_state(session_id, selection)
        stored = self.repository.get_for_selection(session_id, selection_id)
        if stored is not None:
            self._validate_identity(stored, pending)
        consent = stored or pending
        return EvidenceConsentResponse(
            session_id=session_id,
            selection_id=selection_id,
            consent=consent,
        )

    def grant(
        self,
        session_id: str,
        selection_id: str,
        request_id: str,
    ) -> EvidenceConsentResponse:
        selection = self._require_current_selection(session_id, selection_id)
        pending = self._pending_state(session_id, selection)
        existing = self.repository.get_for_selection(session_id, selection_id)
        if existing is not None:
            self._validate_identity(existing, pending)
        if (
            existing is not None
            and existing.status == ConsentStatus.GRANTED
            and existing.scope_version == pending.scope_version
        ):
            return EvidenceConsentResponse(
                session_id=session_id,
                selection_id=selection_id,
                consent=existing,
            )

        timestamp = datetime.now(UTC)
        state = pending.model_copy(
            update={
                "status": ConsentStatus.GRANTED,
                "granted_at": timestamp,
                "updated_at": timestamp,
            }
        )
        saved = self._save(
            session_id=session_id,
            state=state,
            stage=AuditStage.EVIDENCE_CONSENT_GRANTED,
            request_id=request_id,
        )
        return EvidenceConsentResponse(
            session_id=session_id,
            selection_id=selection_id,
            consent=saved,
        )

    def withdraw(
        self,
        session_id: str,
        selection_id: str,
        request_id: str,
    ) -> EvidenceConsentResponse:
        selection = self._require_current_selection(session_id, selection_id)
        pending = self._pending_state(session_id, selection)
        existing = self.repository.get_for_selection(session_id, selection_id)
        if existing is not None:
            self._validate_identity(existing, pending)
        if existing is None or existing.status == ConsentStatus.PENDING:
            raise ResourceConflictError(
                code="EVIDENCE_CONSENT_NOT_GRANTED",
                message="승인되지 않은 Evidence 동의는 철회할 수 없습니다.",
            )
        if existing.status == ConsentStatus.WITHDRAWN:
            return EvidenceConsentResponse(
                session_id=session_id,
                selection_id=selection_id,
                consent=existing,
            )

        timestamp = datetime.now(UTC)
        state = existing.model_copy(
            update={
                "status": ConsentStatus.WITHDRAWN,
                "withdrawn_at": timestamp,
                "updated_at": timestamp,
            }
        )
        saved = self._save(
            session_id=session_id,
            state=state,
            stage=AuditStage.EVIDENCE_CONSENT_WITHDRAWN,
            request_id=request_id,
        )
        return EvidenceConsentResponse(
            session_id=session_id,
            selection_id=selection_id,
            consent=saved,
        )

    def require_granted(
        self,
        session_id: str,
        selection_id: str,
        *,
        scope_version: str | None = None,
    ) -> EvidenceConsentState:
        selection = self._require_current_selection(session_id, selection_id)
        pending = self._pending_state(session_id, selection)
        state = self.repository.get_for_selection(session_id, selection_id)
        if state is not None:
            self._validate_identity(state, pending)
        if (
            state is None
            or state.status != ConsentStatus.GRANTED
            or state.scope_version != pending.scope_version
            or (scope_version is not None and state.scope_version != scope_version)
        ):
            raise ResourceConflictError(
                code="EVIDENCE_CONSENT_REQUIRED",
                message="선택된 자료를 사용하려면 해당 Evidence 범위에 동의해야 합니다.",
            )
        return state

    def is_currently_granted(self, session_id: str, selection_id: str) -> bool:
        selection = self._require_current_selection(session_id, selection_id)
        pending = self._pending_state(session_id, selection)
        state = self.repository.get_for_selection(session_id, selection_id)
        if state is None:
            return False
        self._validate_identity(state, pending)
        return (
            state.status == ConsentStatus.GRANTED and state.scope_version == pending.scope_version
        )

    def _require_current_selection(
        self,
        session_id: str,
        selection_id: str,
    ) -> EvidenceSelectionState:
        self.session_service.get_session(session_id)
        selection = self.selection_repository.get_for_session(session_id, selection_id)
        if selection is None:
            raise ResourceNotFoundError(
                code="EVIDENCE_SELECTION_NOT_FOUND",
                message="Evidence 선택 결과를 찾을 수 없습니다.",
            )
        latest = self.selection_repository.get_latest(session_id)
        if (
            latest is None
            or latest.selection_id != selection_id
            or selection.status != EvidenceSelectionStatus.SELECTED
            or selection.selected_evidence is None
        ):
            raise ResourceConflictError(
                code="EVIDENCE_NOT_SELECTED",
                message="현재 동의 가능한 Evidence 선택 상태가 아닙니다.",
            )
        return selection

    def _pending_state(
        self,
        session_id: str,
        selection: EvidenceSelectionState,
    ) -> EvidenceConsentState:
        selected = selection.selected_evidence
        if selected is None:
            raise ResourceConflictError(
                code="EVIDENCE_NOT_SELECTED",
                message="동의할 Evidence가 선택되지 않았습니다.",
            )
        scope = selected.consent_scope
        if scope is None:
            raise ResourceConflictError(
                code="EVIDENCE_CONSENT_SCOPE_NOT_CONFIGURED",
                message="선택된 Evidence의 동의 범위가 구성되지 않았습니다.",
            )
        identity = hashlib.sha256(f"{session_id}:{selection.selection_id}".encode()).hexdigest()
        return EvidenceConsentState(
            evidence_consent_id=f"evc_{identity[:32]}",
            selection_id=selection.selection_id,
            evidence_type=selected.evidence_type,
            source_type=selected.source_type,
            purpose_code=scope.purpose_code,
            purpose_description=scope.purpose_description,
            data_categories=scope.data_categories,
            period_start=scope.period_start,
            period_end=scope.period_end,
            required=scope.required,
            status=ConsentStatus.PENDING,
            scope_version=scope.scope_version,
        )

    def _validate_identity(
        self,
        state: EvidenceConsentState,
        expected: EvidenceConsentState,
    ) -> None:
        if (
            state.evidence_consent_id != expected.evidence_consent_id
            or state.selection_id != expected.selection_id
            or state.evidence_type != expected.evidence_type
            or state.source_type != expected.source_type
        ):
            raise ResourceConflictError(
                code="EVIDENCE_CONSENT_LINEAGE_INVALID",
                message="Evidence 선택과 동의 이력이 일치하지 않습니다.",
            )
        if state.scope_version == expected.scope_version and (
            state.purpose_code != expected.purpose_code
            or state.purpose_description != expected.purpose_description
            or state.data_categories != expected.data_categories
            or state.period_start != expected.period_start
            or state.period_end != expected.period_end
            or state.required != expected.required
        ):
            raise ResourceConflictError(
                code="EVIDENCE_CONSENT_SCOPE_VERSION_INVALID",
                message="같은 Evidence 동의 버전에 서로 다른 범위가 저장되어 있습니다.",
            )

    def _save(
        self,
        *,
        session_id: str,
        state: EvidenceConsentState,
        stage: AuditStage,
        request_id: str,
    ) -> EvidenceConsentState:
        if state.updated_at is None:
            raise ValueError("saved Evidence consent requires updatedAt")
        snapshot = {
            "selectionId": state.selection_id,
            "evidenceType": state.evidence_type,
            "sourceType": state.source_type.value,
            "purposeCode": state.purpose_code,
            "dataCategories": state.data_categories,
            "periodStart": state.period_start.isoformat(),
            "periodEnd": state.period_end.isoformat(),
            "scopeVersion": state.scope_version,
        }
        snapshot_json = json.dumps(
            snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=stage,
            timestamp=state.updated_at,
            actor=AuditActor.CUSTOMER,
            input_version=state.scope_version,
            input_snapshot_hash=hashlib.sha256(snapshot_json.encode()).hexdigest(),
            output_summary={
                "evidenceConsentId": state.evidence_consent_id,
                "selectionId": state.selection_id,
                "evidenceType": state.evidence_type,
                "status": state.status.value,
                "demoOnly": state.demo_only,
            },
            data_version=state.scope_version,
        )
        return self.repository.save_consent(
            session_id=session_id,
            state=state,
            audit_event=event,
        )

    def readiness(self) -> dict[str, bool]:
        return {"evidence_consent_repository": self.repository.is_ready()}
