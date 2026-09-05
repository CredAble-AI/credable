import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import ResourceConflictError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.evidence_selection_repository import EvidenceSelectionRepository
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.repositories.policy_boundary_repository import PolicyBoundaryRepository
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
from app.schemas.policy_boundary import (
    BoundaryDecision,
    BoundaryStatus,
    EvidenceResolutionState,
    EvidenceResolutionStatus,
)
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
        assessment_repository: AssessmentRepository,
        resolution_repository: PolicyBoundaryRepository,
        submission_repository: EvidenceSubmissionRepository,
        catalog: DemoEvidenceCandidateCatalog,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.boundary_service = boundary_service
        self.data_source_service = data_source_service
        self.assessment_repository = assessment_repository
        self.resolution_repository = resolution_repository
        self.submission_repository = submission_repository
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

        resolution = self._current_resolution(session_id)
        if resolution is not None:
            if resolution.status != EvidenceResolutionStatus.MORE_EVIDENCE_REQUIRED:
                raise ResourceConflictError(
                    code="EVIDENCE_COLLECTION_CLOSED",
                    message="Evidence 수집이 종료되어 추가 Evidence를 선택할 수 없습니다.",
                )
            if resolution.calibration_version is None:
                raise ResourceConflictError(
                    code="EVIDENCE_RESOLUTION_LINEAGE_NOT_READY",
                    message="다음 Evidence 선택에 필요한 불확실성 버전을 확인할 수 없습니다.",
                )
            existing = self.repository.get_by_resolution_id(resolution.resolution_id)
        else:
            existing = self.repository.get_by_boundary_check_id(boundary_check.boundary_check_id)
        if existing is not None:
            return EvidenceSelectionResponse(session_id=session_id, selection=existing)

        data_sources = self.data_source_service.list_states(session_id).data_sources
        excluded_evidence_types = (
            {item.evidence_type for item in self.submission_repository.list_for_session(session_id)}
            if resolution is not None
            else set()
        )
        decision = (
            BoundaryDecision(
                status=BoundaryStatus.AMBIGUOUS,
                possible_routes=resolution.possible_routes,
                crossed_boundary_codes=resolution.crossed_boundary_codes,
                stop_reason=None,
                underwriter_required=False,
            )
            if resolution is not None
            else boundary_check.decision
        )
        state, selected_evidence_value = self._build_state(
            boundary_check_id=boundary_check.boundary_check_id,
            resolution_id=resolution.resolution_id if resolution is not None else None,
            decision=decision,
            data_sources=data_sources,
            iteration=self.repository.count_selections(session_id) + 1,
            calibration_version=(
                resolution.calibration_version
                if resolution is not None
                else boundary_check.calibration_version
            ),
            boundary_policy_version=(
                resolution.boundary_policy_version
                if resolution is not None
                else boundary_check.policy_version
            ),
            excluded_evidence_types=excluded_evidence_types,
        )
        selection_input = resolution if resolution is not None else boundary_check
        selection_input_json = json.dumps(
            selection_input.model_dump(mode="json", by_alias=True),
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
        if state.resolution_id is not None:
            output_summary["resolutionId"] = state.resolution_id
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
            input_version=state.resolution_id or boundary_check.boundary_check_id,
            input_snapshot_hash=hashlib.sha256(selection_input_json.encode()).hexdigest(),
            output_summary=output_summary,
            data_version=(
                resolution.supplemental_assessment_id
                if resolution is not None
                else boundary_check.input_snapshot_id
            ),
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
        boundary_check_id: str,
        resolution_id: str | None,
        decision: BoundaryDecision,
        data_sources: list[DataSourceState],
        iteration: int,
        calibration_version: str,
        boundary_policy_version: str,
        excluded_evidence_types: set[str],
    ) -> tuple[EvidenceSelectionState, float | None]:
        selected_at = datetime.now(UTC)
        common = {
            "selection_id": f"evs_{uuid4().hex}",
            "boundary_check_id": boundary_check_id,
            "resolution_id": resolution_id,
            "iteration": iteration,
            "selected_at": selected_at,
            "calibration_version": calibration_version,
            "boundary_policy_version": boundary_policy_version,
            "selection_policy_version": self.catalog.selection_policy_version,
        }
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
        definitions = [
            item
            for item in self.catalog.candidates_for(decision.crossed_boundary_codes)
            if item.evidence_type not in excluded_evidence_types
        ]
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
                    stop_reason=(
                        "NO_NEW_USEFUL_EVIDENCE"
                        if excluded_evidence_types
                        else "NO_USEFUL_EVIDENCE"
                    ),
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

    def _current_resolution(self, session_id: str) -> EvidenceResolutionState | None:
        supplemental = self.assessment_repository.get_latest_supplemental(session_id)
        if supplemental is None:
            return None

        comparison = self.assessment_repository.get_latest_comparison(session_id)
        resolution = self.resolution_repository.get_latest_resolution(session_id)
        if (
            comparison is None
            or comparison.supplemental_assessment_id != supplemental.supplemental_assessment_id
            or resolution is None
            or resolution.comparison_id != comparison.comparison_id
            or resolution.supplemental_assessment_id != supplemental.supplemental_assessment_id
        ):
            raise ResourceConflictError(
                code="EVIDENCE_RESOLUTION_NOT_READY",
                message="현재 보완평가와 연결된 Evidence 수집 판단이 필요합니다.",
            )
        return resolution

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
