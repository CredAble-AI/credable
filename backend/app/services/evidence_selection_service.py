import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import ResourceConflictError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.evidence_quality_repository import EvidenceQualityRepository
from app.repositories.evidence_selection_repository import EvidenceSelectionRepository
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.repositories.feature_snapshot_repository import FeatureSnapshotRepository
from app.repositories.policy_boundary_repository import PolicyBoundaryRepository
from app.schemas.assessment import ExistingAssessmentReference
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.data_source import DataSourceState, RetrievalStatus, VerificationStatus
from app.schemas.evidence_quality import EvidenceQualityState, EvidenceQualityStatus
from app.schemas.evidence_selection import (
    DemoEvidenceCandidateCatalogData,
    EvidenceAvailability,
    EvidenceCandidateDefinition,
    EvidenceSelectionResponse,
    EvidenceSelectionState,
    EvidenceSelectionStatus,
    SelectedEvidenceCandidate,
)
from app.schemas.feature_snapshot import AssessmentFeatureSnapshot, FeatureValueStatus
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

    @property
    def max_evidence_requests(self) -> int:
        return self._load().max_evidence_requests

    def candidates_for(
        self,
        boundary_codes: list[str],
        information_gap_codes: list[str],
    ) -> list[EvidenceCandidateDefinition]:
        required_codes = set(boundary_codes)
        required_gaps = set(information_gap_codes)
        return [
            candidate
            for candidate in self._load().candidates
            if required_codes.intersection(candidate.boundary_codes)
            and required_gaps.intersection(candidate.applicable_information_gap_codes)
        ]

    def baseline_information_coverage(
        self,
        feature_snapshot: AssessmentFeatureSnapshot,
    ) -> list[str]:
        available_feature_codes = {
            item.feature_code
            for item in feature_snapshot.feature_values
            if item.status == FeatureValueStatus.AVAILABLE
        }
        return sorted(
            rule.information_content_code
            for rule in self._load().baseline_information_coverage_rules
            if set(rule.required_feature_codes).issubset(available_feature_codes)
        )

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
        quality_repository: EvidenceQualityRepository,
        feature_snapshot_repository: FeatureSnapshotRepository,
        catalog: DemoEvidenceCandidateCatalog,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.boundary_service = boundary_service
        self.data_source_service = data_source_service
        self.assessment_repository = assessment_repository
        self.resolution_repository = resolution_repository
        self.submission_repository = submission_repository
        self.quality_repository = quality_repository
        self.feature_snapshot_repository = feature_snapshot_repository
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

        latest_selection = self.repository.get_latest(session_id)
        rejected_quality = self._rejected_quality_for_latest_selection(
            session_id,
            latest_selection,
        )
        resolution = None if rejected_quality is not None else self._current_resolution(session_id)
        if rejected_quality is not None:
            existing = self.repository.get_by_rejected_quality_check_id(
                rejected_quality.quality_check_id
            )
        elif resolution is not None:
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
            existing = (
                latest_selection
                if latest_selection is not None
                and latest_selection.boundary_check_id == boundary_check.boundary_check_id
                else self.repository.get_by_boundary_check_id(boundary_check.boundary_check_id)
            )
        if existing is not None:
            return EvidenceSelectionResponse(session_id=session_id, selection=existing)

        data_sources = self.data_source_service.list_states(session_id).data_sources
        excluded_evidence_types = (
            {item.evidence_type for item in self.submission_repository.list_for_session(session_id)}
            if resolution is not None or rejected_quality is not None
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
            else self._decision_for_rejected_selection(
                session_id,
                latest_selection,
                boundary_check.decision,
            )
            if rejected_quality is not None
            else boundary_check.decision
        )
        baseline = self.assessment_repository.get_for_session(
            session_id,
            boundary_check.assessment_id,
        )
        source_assessment = baseline.source_assessment if baseline is not None else None
        baseline_feature_snapshot_id: str | None = None
        baseline_information_coverage_codes: list[str] | None = None
        if baseline is not None and baseline.assessment_id is not None:
            baseline_input = self.assessment_repository.get_snapshot(baseline.assessment_id)
            if baseline_input is not None and baseline_input.feature_snapshot is not None:
                feature_snapshot = self.feature_snapshot_repository.get(
                    baseline_input.feature_snapshot.feature_snapshot_id
                )
                if feature_snapshot is not None and feature_snapshot.session_id == session_id:
                    baseline_feature_snapshot_id = feature_snapshot.feature_snapshot_id
                    baseline_information_coverage_codes = (
                        self.catalog.baseline_information_coverage(feature_snapshot)
                    )
        state, selected_evidence_value = self._build_state(
            boundary_check_id=boundary_check.boundary_check_id,
            resolution_id=resolution.resolution_id if resolution is not None else None,
            rejected_quality_check_id=(
                rejected_quality.quality_check_id if rejected_quality is not None else None
            ),
            decision=decision,
            data_sources=data_sources,
            iteration=self.repository.count_selections(session_id) + 1,
            calibration_version=(
                resolution.calibration_version
                if resolution is not None
                else latest_selection.calibration_version
                if rejected_quality is not None and latest_selection is not None
                else boundary_check.calibration_version
            ),
            boundary_policy_version=(
                resolution.boundary_policy_version
                if resolution is not None
                else latest_selection.boundary_policy_version
                if rejected_quality is not None and latest_selection is not None
                else boundary_check.policy_version
            ),
            excluded_evidence_types=excluded_evidence_types,
            source_assessment=source_assessment,
            baseline_feature_snapshot_id=baseline_feature_snapshot_id,
            baseline_information_coverage_codes=baseline_information_coverage_codes,
        )
        selection_input = resolution or rejected_quality or boundary_check
        selection_input_json = json.dumps(
            {
                "decisionInput": selection_input.model_dump(mode="json", by_alias=True),
                "boundaryDecision": decision.model_dump(mode="json", by_alias=True),
                "sourceAssessment": (
                    source_assessment.model_dump(mode="json", by_alias=True)
                    if source_assessment is not None
                    else None
                ),
                "baselineFeatureSnapshotId": baseline_feature_snapshot_id,
                "baselineInformationCoverageCodes": baseline_information_coverage_codes,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        output_summary: dict[str, str | bool | int | float] = {
            "selectionStatus": state.status.value,
            "iteration": state.iteration,
            "maxEvidenceRequests": state.max_evidence_requests,
            "evaluatedCandidateCount": state.evaluated_candidate_count,
            "underwriterRequired": state.underwriter_required,
            "calibrationVersion": state.calibration_version,
            "informationGapCount": len(state.information_gap_codes),
            "baselineInformationCoverageCount": len(state.baseline_information_coverage_codes),
            "demoOnly": state.demo_only,
        }
        if state.source_credit_assessment_id is not None:
            output_summary["sourceCreditAssessmentId"] = state.source_credit_assessment_id
        if state.resolution_id is not None:
            output_summary["resolutionId"] = state.resolution_id
        if state.rejected_quality_check_id is not None:
            output_summary["rejectedQualityCheckId"] = state.rejected_quality_check_id
        if state.selected_evidence is not None:
            output_summary.update(
                {
                    "selectedEvidenceType": state.selected_evidence.evidence_type,
                    "evidenceValue": selected_evidence_value,
                    "matchedInformationGapCount": len(
                        state.selected_evidence.matched_information_gap_codes
                    ),
                    "novelInformationCount": len(state.selected_evidence.novel_information_codes),
                    "overlappingInformationCount": len(
                        state.selected_evidence.overlapping_information_codes
                    ),
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
            input_version=(
                state.resolution_id
                or state.rejected_quality_check_id
                or boundary_check.boundary_check_id
            ),
            input_snapshot_hash=hashlib.sha256(selection_input_json.encode()).hexdigest(),
            output_summary=output_summary,
            data_version=(
                resolution.supplemental_assessment_id
                if resolution is not None
                else rejected_quality.data_version
                if rejected_quality is not None
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
        rejected_quality_check_id: str | None,
        decision: BoundaryDecision,
        data_sources: list[DataSourceState],
        iteration: int,
        calibration_version: str,
        boundary_policy_version: str,
        excluded_evidence_types: set[str],
        source_assessment: ExistingAssessmentReference | None,
        baseline_feature_snapshot_id: str | None,
        baseline_information_coverage_codes: list[str] | None,
    ) -> tuple[EvidenceSelectionState, float | None]:
        selected_at = datetime.now(UTC)
        common = {
            "selection_id": f"evs_{uuid4().hex}",
            "boundary_check_id": boundary_check_id,
            "resolution_id": resolution_id,
            "rejected_quality_check_id": rejected_quality_check_id,
            "iteration": iteration,
            "max_evidence_requests": self.catalog.max_evidence_requests,
            "selected_at": selected_at,
            "calibration_version": calibration_version,
            "boundary_policy_version": boundary_policy_version,
            "selection_policy_version": self.catalog.selection_policy_version,
            "source_credit_assessment_id": (
                source_assessment.credit_assessment_id if source_assessment is not None else None
            ),
            "information_gap_codes": (
                source_assessment.reason_codes if source_assessment is not None else []
            ),
            "baseline_feature_snapshot_id": baseline_feature_snapshot_id,
            "baseline_information_coverage_codes": (
                baseline_information_coverage_codes
                if baseline_information_coverage_codes is not None
                else []
            ),
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
        if source_assessment is None:
            return (
                EvidenceSelectionState(
                    **common,
                    status=EvidenceSelectionStatus.HUMAN_REVIEW,
                    evaluated_candidate_count=0,
                    stop_reason="SOURCE_ASSESSMENT_LINEAGE_NOT_READY",
                    underwriter_required=True,
                ),
                None,
            )
        if not source_assessment.reason_codes:
            return (
                EvidenceSelectionState(
                    **common,
                    status=EvidenceSelectionStatus.HUMAN_REVIEW,
                    evaluated_candidate_count=0,
                    stop_reason="SOURCE_INFORMATION_GAP_NOT_AVAILABLE",
                    underwriter_required=True,
                ),
                None,
            )
        if baseline_information_coverage_codes is None:
            return (
                EvidenceSelectionState(
                    **common,
                    status=EvidenceSelectionStatus.HUMAN_REVIEW,
                    evaluated_candidate_count=0,
                    stop_reason="BASELINE_INFORMATION_COVERAGE_NOT_READY",
                    underwriter_required=True,
                ),
                None,
            )

        source_states = {item.source_type: item for item in data_sources}
        applicable_definitions = self.catalog.candidates_for(
            decision.crossed_boundary_codes,
            source_assessment.reason_codes,
        )

        definitions = [
            item
            for item in applicable_definitions
            if item.evidence_type not in excluded_evidence_types
        ]
        candidates = [
            self._score_candidate(
                definition,
                decision.crossed_boundary_codes,
                source_assessment.reason_codes,
                baseline_information_coverage_codes,
                source_states.get(definition.source_type),
            )
            for definition in definitions
        ]
        useful = [
            (candidate, evidence_value)
            for candidate, evidence_value in candidates
            if candidate.availability != EvidenceAvailability.UNAVAILABLE
            and evidence_value is not None
            and evidence_value > 0
        ]
        useful.sort(key=lambda item: (-item[1], item[0].evidence_type))
        if not useful:
            if not applicable_definitions:
                stop_reason = "NO_CANDIDATE_FOR_INFORMATION_GAP"
            elif not definitions:
                stop_reason = "NO_NEW_USEFUL_EVIDENCE"
            elif all(not item.novel_information_codes for item, _ in candidates):
                stop_reason = "NO_NOVEL_EVIDENCE"
            else:
                stop_reason = "NO_USEFUL_EVIDENCE"
            return (
                EvidenceSelectionState(
                    **common,
                    status=EvidenceSelectionStatus.HUMAN_REVIEW,
                    evaluated_candidate_count=len(candidates),
                    stop_reason=stop_reason,
                    underwriter_required=True,
                ),
                None,
            )
        if iteration > self.catalog.max_evidence_requests:
            return (
                EvidenceSelectionState(
                    **common,
                    status=EvidenceSelectionStatus.HUMAN_REVIEW,
                    evaluated_candidate_count=len(candidates),
                    stop_reason="EVIDENCE_REQUEST_LIMIT_REACHED",
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

    def _rejected_quality_for_latest_selection(
        self,
        session_id: str,
        selection: EvidenceSelectionState | None,
    ) -> EvidenceQualityState | None:
        if selection is None or selection.status != EvidenceSelectionStatus.SELECTED:
            return None
        submission = self.submission_repository.get_by_selection_id(selection.selection_id)
        if submission is None:
            return None
        quality = self.quality_repository.get_for_submission(
            session_id,
            submission.submission_id,
        )
        if quality is None or quality.status != EvidenceQualityStatus.REJECTED:
            return None
        return quality

    def _decision_for_rejected_selection(
        self,
        session_id: str,
        selection: EvidenceSelectionState | None,
        fallback: BoundaryDecision,
    ) -> BoundaryDecision:
        if selection is None or selection.resolution_id is None:
            return fallback
        resolution_record = self.resolution_repository.get_resolution_by_id(selection.resolution_id)
        if resolution_record is None or resolution_record[0] != session_id:
            raise ResourceConflictError(
                code="EVIDENCE_SELECTION_LINEAGE_NOT_READY",
                message="품질 탈락 후 다음 Evidence 선택에 필요한 수집 판단을 확인할 수 없습니다.",
            )
        resolution = resolution_record[1]
        if resolution.status != EvidenceResolutionStatus.MORE_EVIDENCE_REQUIRED:
            raise ResourceConflictError(
                code="EVIDENCE_COLLECTION_CLOSED",
                message="Evidence 수집이 종료되어 추가 Evidence를 선택할 수 없습니다.",
            )
        return BoundaryDecision(
            status=BoundaryStatus.AMBIGUOUS,
            possible_routes=resolution.possible_routes,
            crossed_boundary_codes=resolution.crossed_boundary_codes,
            stop_reason=None,
            underwriter_required=False,
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
        information_gap_codes: list[str],
        baseline_information_coverage_codes: list[str],
        source_state: DataSourceState | None,
    ) -> tuple[SelectedEvidenceCandidate, float | None]:
        information_content_codes = set(definition.information_content_codes)
        overlapping_information_codes = sorted(
            information_content_codes.intersection(baseline_information_coverage_codes)
        )
        novel_information_codes = sorted(
            information_content_codes.difference(baseline_information_coverage_codes)
        )
        evidence_value = (
            definition.boundary_resolution_value * definition.quality_reliability
            - definition.customer_effort
            - definition.privacy_sensitivity
            - definition.acquisition_delay
            - definition.acquisition_cost
        )
        if not any(code in definition.boundary_codes for code in crossed_boundary_codes):
            raise ValueError("candidate must cover a crossed policy boundary")
        matched_information_gap_codes = sorted(
            set(information_gap_codes).intersection(definition.applicable_information_gap_codes)
        )
        if not matched_information_gap_codes:
            raise ValueError("candidate must apply to a source assessment information gap")
        return (
            SelectedEvidenceCandidate(
                evidence_type=definition.evidence_type,
                display_name=definition.display_name,
                description=definition.description,
                source_type=definition.source_type,
                collection_mode=definition.collection_mode,
                availability=self._availability(source_state),
                rationale_codes=definition.rationale_codes,
                matched_information_gap_codes=matched_information_gap_codes,
                information_content_codes=sorted(information_content_codes),
                novel_information_codes=novel_information_codes,
                overlapping_information_codes=overlapping_information_codes,
                consent_scope=definition.consent_scope,
            ),
            round(evidence_value, 6) if novel_information_codes else None,
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
