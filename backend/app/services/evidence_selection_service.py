import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import ResourceConflictError
from app.repositories.evidence_selection_repository import EvidenceSelectionRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.data_source import DataSourceState, RetrievalStatus, VerificationStatus
from app.schemas.evidence_selection import (
    DemoEvidenceCandidateCatalogData,
    EvidenceAvailability,
    EvidenceCandidateDefinition,
    EvidenceSelectionResponse,
    EvidenceSelectionState,
    EvidenceSelectionStatus,
    SelectedEvidenceCandidate,
)
from app.schemas.policy_boundary import BoundaryStatus, PolicyBoundaryCheckState
from app.services.data_source_service import DataSourceService
from app.services.policy_boundary_service import PolicyBoundaryService
from app.services.session_service import CustomerSessionService


class DemoEvidenceCandidateCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoEvidenceCandidateCatalogData | None = None

    @property
    def selection_policy_version(self) -> str:
        return self._load().selection_policy_version

    def candidates_for(self, boundary_codes: list[str]) -> list[EvidenceCandidateDefinition]:
        required_codes = set(boundary_codes)
        return [
            candidate
            for candidate in self._load().candidates
            if required_codes.intersection(candidate.boundary_codes)
        ]

    def is_ready(self) -> bool:
        try:
            self._load()
        except (OSError, ValueError):
            return False
        return True

    def _load(self) -> DemoEvidenceCandidateCatalogData:
        if self._catalog is None:
            self._catalog = DemoEvidenceCandidateCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
        return self._catalog


class EvidenceSelectionService:
    def __init__(
        self,
        repository: EvidenceSelectionRepository,
        session_service: CustomerSessionService,
        boundary_service: PolicyBoundaryService,
        data_source_service: DataSourceService,
        catalog: DemoEvidenceCandidateCatalog,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.boundary_service = boundary_service
        self.data_source_service = data_source_service
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> EvidenceSelectionResponse:
        self.session_service.get_session(session_id)
        return EvidenceSelectionResponse(
            session_id=session_id,
            selection=self.repository.get_latest(session_id),
        )

    def select_next(self, session_id: str, request_id: str) -> EvidenceSelectionResponse:
        self.session_service.get_session(session_id)
        boundary_check = self.boundary_service.get_latest(session_id).boundary_check
        if boundary_check is None:
            raise ResourceConflictError(
                code="POLICY_BOUNDARY_CHECK_NOT_READY",
                message="최소 증빙 선택 전에 정책 경계 판정이 필요합니다.",
            )

        existing = self.repository.get_by_boundary_check_id(boundary_check.boundary_check_id)
        if existing is not None:
            return EvidenceSelectionResponse(session_id=session_id, selection=existing)

        data_sources = self.data_source_service.list_states(session_id).data_sources
        state, selected_evidence_value = self._build_state(
            boundary_check=boundary_check,
            data_sources=data_sources,
            iteration=self.repository.count_selections(session_id) + 1,
        )
        boundary_json = json.dumps(
            boundary_check.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        output_summary: dict[str, str | bool | int | float] = {
            "selectionStatus": state.status.value,
            "iteration": state.iteration,
            "evaluatedCandidateCount": state.evaluated_candidate_count,
            "underwriterRequired": state.underwriter_required,
            "calibrationVersion": state.calibration_version,
            "demoOnly": state.demo_only,
        }
        if state.selected_evidence is not None:
            output_summary.update(
                {
                    "selectedEvidenceType": state.selected_evidence.evidence_type,
                    "evidenceValue": selected_evidence_value,
                }
            )
        if state.stop_reason is not None:
            output_summary["stopReason"] = state.stop_reason
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.EVIDENCE_SELECTED,
            timestamp=state.selected_at,
            actor=AuditActor.SYSTEM,
            input_version=boundary_check.boundary_check_id,
            input_snapshot_hash=hashlib.sha256(boundary_json.encode()).hexdigest(),
            output_summary=output_summary,
            data_version=boundary_check.input_snapshot_id,
            policy_version=state.selection_policy_version,
        )
        saved = self.repository.save_selection(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return EvidenceSelectionResponse(session_id=session_id, selection=saved)

    def _build_state(
        self,
        *,
        boundary_check: PolicyBoundaryCheckState,
        data_sources: list[DataSourceState],
        iteration: int,
    ) -> tuple[EvidenceSelectionState, float | None]:
        selected_at = datetime.now(UTC)
        common = {
            "selection_id": f"evs_{uuid4().hex}",
            "boundary_check_id": boundary_check.boundary_check_id,
            "iteration": iteration,
            "selected_at": selected_at,
            "calibration_version": boundary_check.calibration_version,
            "boundary_policy_version": boundary_check.policy_version,
            "selection_policy_version": self.catalog.selection_policy_version,
        }
        decision = boundary_check.decision
        if decision.status == BoundaryStatus.STABLE:
            return (
                EvidenceSelectionState(
                    **common,
                    status=EvidenceSelectionStatus.NOT_REQUIRED,
                    evaluated_candidate_count=0,
                    stop_reason="PATH_STABLE",
                    underwriter_required=False,
                ),
                None,
            )
        if decision.status == BoundaryStatus.POLICY_BLOCKED:
            return (
                EvidenceSelectionState(
                    **common,
                    status=EvidenceSelectionStatus.POLICY_BLOCKED,
                    evaluated_candidate_count=0,
                    stop_reason=decision.stop_reason or "POLICY_BLOCKED",
                    underwriter_required=True,
                ),
                None,
            )

        source_states = {item.source_type: item for item in data_sources}
        definitions = self.catalog.candidates_for(decision.crossed_boundary_codes)
        candidates = [
            self._score_candidate(
                definition,
                decision.crossed_boundary_codes,
                source_states.get(definition.source_type),
            )
            for definition in definitions
        ]
        useful = [
            (candidate, evidence_value)
            for candidate, evidence_value in candidates
            if candidate.availability != EvidenceAvailability.UNAVAILABLE and evidence_value > 0
        ]
        useful.sort(key=lambda item: (-item[1], item[0].evidence_type))
        if not useful:
            return (
                EvidenceSelectionState(
                    **common,
                    status=EvidenceSelectionStatus.HUMAN_REVIEW,
                    evaluated_candidate_count=len(candidates),
                    stop_reason="NO_USEFUL_EVIDENCE",
                    underwriter_required=True,
                ),
                None,
            )
        selected, selected_value = useful[0]
        return (
            EvidenceSelectionState(
                **common,
                status=EvidenceSelectionStatus.SELECTED,
                selected_evidence=selected,
                evaluated_candidate_count=len(candidates),
                stop_reason=None,
                underwriter_required=False,
            ),
            selected_value,
        )

    def _score_candidate(
        self,
        definition: EvidenceCandidateDefinition,
        crossed_boundary_codes: list[str],
        source_state: DataSourceState | None,
    ) -> tuple[SelectedEvidenceCandidate, float]:
        evidence_value = (
            definition.boundary_resolution_value * definition.quality_reliability
            - definition.customer_effort
            - definition.privacy_sensitivity
            - definition.acquisition_delay
            - definition.acquisition_cost
        )
        if not any(code in definition.boundary_codes for code in crossed_boundary_codes):
            raise ValueError("candidate must cover a crossed policy boundary")
        return (
            SelectedEvidenceCandidate(
                evidence_type=definition.evidence_type,
                display_name=definition.display_name,
                description=definition.description,
                source_type=definition.source_type,
                availability=self._availability(source_state),
                rationale_codes=definition.rationale_codes,
            ),
            round(evidence_value, 6),
        )

    def _availability(self, state: DataSourceState | None) -> EvidenceAvailability:
        if state is None:
            return EvidenceAvailability.UNAVAILABLE
        if (
            state.retrieval_status == RetrievalStatus.RETRIEVED
            and state.verification_status == VerificationStatus.VERIFIED
        ):
            return EvidenceAvailability.AVAILABLE
        if state.retrieval_status == RetrievalStatus.CONSENT_REQUIRED:
            return EvidenceAvailability.CONSENT_REQUIRED
        if state.retrieval_status == RetrievalStatus.NOT_REQUESTED:
            return EvidenceAvailability.REQUESTABLE
        return EvidenceAvailability.UNAVAILABLE

    def readiness(self) -> dict[str, bool]:
        return {
            "evidence_selection_repository": self.repository.is_ready(),
            "evidence_candidate_catalog": self.catalog.is_ready(),
        }
