import hashlib
import json
from datetime import UTC, datetime
from typing import NoReturn
from uuid import uuid4

from app.adapters.assessment_adapter import AssessmentAdapter, SupplementalAssessmentAdapter
from app.core.errors import EvidenceSubmissionNotFoundError, ResourceConflictError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.evidence_quality_repository import EvidenceQualityRepository
from app.repositories.evidence_selection_repository import EvidenceSelectionRepository
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.repositories.policy_boundary_repository import PolicyBoundaryRepository
from app.schemas.assessment import (
    AcceptedEvidenceSnapshot,
    AdapterAssessmentResult,
    AssessmentComparisonBasis,
    AssessmentComparisonResponse,
    AssessmentComparisonState,
    AssessmentInputSnapshot,
    AssessmentResponse,
    AssessmentState,
    AssessmentStatus,
    AssessmentUncertainty,
    AssessmentUncertaintyChange,
    SupplementalAssessmentInputSnapshot,
    SupplementalAssessmentResponse,
    SupplementalAssessmentState,
)
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.evidence_quality import EvidenceQualityStatus
from app.schemas.evidence_selection import EvidenceSelectionStatus
from app.schemas.policy_boundary import BoundaryStatus
from app.services.data_source_service import DataSourceService
from app.services.session_service import CustomerSessionService


def compare_uncertainties(
    before: AssessmentUncertainty | None,
    after: AssessmentUncertainty | None,
) -> tuple[AssessmentComparisonBasis, AssessmentUncertaintyChange, list[str]]:
    if before is None or after is None:
        return (
            AssessmentComparisonBasis.NOT_COMPARABLE,
            AssessmentUncertaintyChange.NOT_COMPARABLE,
            ["ASSESSMENT_UNCERTAINTY_NOT_AVAILABLE"],
        )
    if before.calibration_mode != after.calibration_mode:
        return (
            AssessmentComparisonBasis.NOT_COMPARABLE,
            AssessmentUncertaintyChange.NOT_COMPARABLE,
            ["CALIBRATION_MODE_MISMATCH"],
        )
    if before.calibration_version != after.calibration_version:
        return (
            AssessmentComparisonBasis.NOT_COMPARABLE,
            AssessmentUncertaintyChange.NOT_COMPARABLE,
            ["CALIBRATION_VERSION_MISMATCH"],
        )
    if before.grade_set and after.grade_set:
        before_grades = set(before.grade_set)
        after_grades = set(after.grade_set)
        if before_grades == after_grades:
            change = AssessmentUncertaintyChange.UNCHANGED
            code = "GRADE_SET_UNCHANGED"
        elif after_grades < before_grades:
            change = AssessmentUncertaintyChange.NARROWED
            code = "GRADE_SET_PROPER_SUBSET"
        elif before_grades < after_grades:
            change = AssessmentUncertaintyChange.EXPANDED
            code = "GRADE_SET_PROPER_SUPERSET"
        else:
            change = AssessmentUncertaintyChange.SHIFTED
            code = "GRADE_SET_SHIFTED"
        return AssessmentComparisonBasis.GRADE_SET, change, [code]
    if (
        before.lower_bound is not None
        and before.upper_bound is not None
        and after.lower_bound is not None
        and after.upper_bound is not None
    ):
        before_interval = (before.lower_bound, before.upper_bound)
        after_interval = (after.lower_bound, after.upper_bound)
        if before_interval == after_interval:
            change = AssessmentUncertaintyChange.UNCHANGED
            code = "NUMERIC_INTERVAL_UNCHANGED"
        elif after.lower_bound >= before.lower_bound and after.upper_bound <= before.upper_bound:
            change = AssessmentUncertaintyChange.NARROWED
            code = "NUMERIC_INTERVAL_CONTAINED"
        elif before.lower_bound >= after.lower_bound and before.upper_bound <= after.upper_bound:
            change = AssessmentUncertaintyChange.EXPANDED
            code = "NUMERIC_INTERVAL_EXPANDED"
        else:
            change = AssessmentUncertaintyChange.SHIFTED
            code = "NUMERIC_INTERVAL_SHIFTED"
        return AssessmentComparisonBasis.NUMERIC_INTERVAL, change, [code]
    return (
        AssessmentComparisonBasis.NOT_COMPARABLE,
        AssessmentUncertaintyChange.NOT_COMPARABLE,
        ["UNCERTAINTY_REPRESENTATION_MISMATCH"],
    )


class AssessmentService:
    def __init__(
        self,
        repository: AssessmentRepository,
        session_service: CustomerSessionService,
        data_source_service: DataSourceService,
        adapter: AssessmentAdapter,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.data_source_service = data_source_service
        self.adapter = adapter

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> AssessmentResponse:
        self.session_service.get_session(session_id)
        state = self.repository.get_latest(session_id)
        if state is None:
            state = AssessmentState(status=AssessmentStatus.NOT_RUN)
        return AssessmentResponse(session_id=session_id, assessment=state)

    def run(self, session_id: str, request_id: str) -> AssessmentResponse:
        session = self.session_service.get_session(session_id).session
        data_sources = self.data_source_service.list_states(session_id).data_sources
        snapshot = AssessmentInputSnapshot(
            session_id=session_id,
            demo_profile_id=session.demo_profile.demo_profile_id,
            data_sources=data_sources,
        )
        snapshot_json = json.dumps(
            snapshot.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
        snapshot_id = f"dss_{snapshot_hash}"

        try:
            result = self.adapter.run(snapshot)
        except Exception:
            result = AdapterAssessmentResult(
                status=AssessmentStatus.FAILED,
                reason_code="ASSESSMENT_ADAPTER_ERROR",
            )

        calculated_at = datetime.now(UTC)
        state = AssessmentState(
            assessment_id=f"asm_{uuid4().hex}",
            status=result.status,
            calculated_at=calculated_at,
            input_snapshot_id=snapshot_id,
            model_version=result.model_version,
            reason_code=result.reason_code,
            uncertainty=result.uncertainty,
        )
        output_summary: dict[str, str | bool] = {
            "assessmentStatus": state.status.value,
            "demoOnly": state.demo_only,
        }
        if state.uncertainty is not None:
            output_summary.update(
                {
                    "calibrationMode": state.uncertainty.calibration_mode.value,
                    "calibrationVersion": state.uncertainty.calibration_version,
                }
            )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.ASSESSMENT_RUN,
            timestamp=calculated_at,
            actor=AuditActor.SYSTEM,
            input_version=snapshot_id,
            input_snapshot_hash=snapshot_hash,
            output_summary=output_summary,
            data_version=snapshot_id,
            model_version=state.model_version,
        )
        saved = self.repository.save_execution(
            session_id=session_id,
            state=state,
            snapshot=snapshot,
            audit_event=audit_event,
        )
        return AssessmentResponse(session_id=session_id, assessment=saved)

    def readiness(self) -> dict[str, bool]:
        return {
            "assessment_repository": self.repository.is_ready(),
            "assessment_adapter": self.adapter.is_ready(),
        }


class SupplementalAssessmentService:
    def __init__(
        self,
        repository: AssessmentRepository,
        session_service: CustomerSessionService,
        quality_repository: EvidenceQualityRepository,
        submission_repository: EvidenceSubmissionRepository,
        selection_repository: EvidenceSelectionRepository,
        boundary_repository: PolicyBoundaryRepository,
        adapter: SupplementalAssessmentAdapter,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.quality_repository = quality_repository
        self.submission_repository = submission_repository
        self.selection_repository = selection_repository
        self.boundary_repository = boundary_repository
        self.adapter = adapter

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> SupplementalAssessmentResponse:
        self.session_service.get_session(session_id)
        return SupplementalAssessmentResponse(
            session_id=session_id,
            supplemental_assessment=self.repository.get_latest_supplemental(session_id),
        )

    def run(
        self,
        session_id: str,
        submission_id: str,
        request_id: str,
    ) -> SupplementalAssessmentResponse:
        session = self.session_service.get_session(session_id).session
        submission = self.submission_repository.get_for_session(session_id, submission_id)
        if submission is None:
            raise EvidenceSubmissionNotFoundError(submission_id)

        quality = self.quality_repository.get_for_submission(session_id, submission_id)
        if quality is None:
            self._conflict(
                "EVIDENCE_QUALITY_NOT_READY",
                "보완평가 전에 Evidence 품질 검증이 필요합니다.",
            )
        if (
            quality.submission_id != submission.submission_id
            or quality.evidence_type != submission.evidence_type
            or quality.submission_snapshot_hash != submission.submission_snapshot_hash
            or quality.data_version != submission.data_version
        ):
            self._conflict(
                "EVIDENCE_QUALITY_LINEAGE_INVALID",
                "Evidence 제출과 품질 검증 이력이 일치하지 않습니다.",
            )
        if (
            quality.status != EvidenceQualityStatus.ACCEPTED
            or not quality.eligible_for_reassessment
        ):
            self._conflict(
                "EVIDENCE_QUALITY_NOT_ACCEPTED",
                "품질 검증을 통과한 Evidence만 보완평가에 사용할 수 있습니다.",
            )

        existing = self.repository.get_supplemental_by_quality_check_id(quality.quality_check_id)
        if existing is not None:
            return SupplementalAssessmentResponse(
                session_id=session_id,
                supplemental_assessment=existing,
            )

        selection = self.selection_repository.get_latest(session_id)
        boundary = self.boundary_repository.get_latest(session_id)
        baseline = self.repository.get_latest(session_id)
        if (
            selection is None
            or selection.selection_id != submission.selection_id
            or selection.status != EvidenceSelectionStatus.SELECTED
            or selection.selected_evidence is None
            or selection.selected_evidence.evidence_type != submission.evidence_type
            or selection.selected_evidence.source_type != submission.source_type
            or boundary is None
            or boundary.boundary_check_id != selection.boundary_check_id
            or boundary.decision.status != BoundaryStatus.AMBIGUOUS
            or baseline is None
            or baseline.assessment_id != boundary.assessment_id
            or baseline.status != AssessmentStatus.COMPLETED
            or baseline.input_snapshot_id is None
            or baseline.uncertainty is None
        ):
            self._conflict(
                "SUPPLEMENTAL_ASSESSMENT_LINEAGE_NOT_READY",
                "현재 기준평가와 연결된 Evidence 판단 이력이 필요합니다.",
            )
        baseline_snapshot = self.repository.get_snapshot(baseline.assessment_id)
        if (
            baseline_snapshot is None
            or baseline_snapshot.session_id != session_id
            or baseline_snapshot.demo_profile_id != session.demo_profile.demo_profile_id
        ):
            self._conflict(
                "BASELINE_ASSESSMENT_SNAPSHOT_NOT_FOUND",
                "기준평가 입력 Snapshot을 확인할 수 없습니다.",
            )

        accepted_evidence = AcceptedEvidenceSnapshot(
            quality_check_id=quality.quality_check_id,
            submission_id=submission.submission_id,
            selection_id=selection.selection_id,
            boundary_check_id=boundary.boundary_check_id,
            evidence_type=submission.evidence_type,
            source_type=submission.source_type,
            observed_at=submission.observed_at,
            checked_at=quality.checked_at,
            submission_snapshot_hash=submission.submission_snapshot_hash,
            evidence_data_version=submission.data_version,
            quality_policy_version=quality.quality_policy_version,
        )
        snapshot = SupplementalAssessmentInputSnapshot(
            session_id=session_id,
            demo_profile_id=session.demo_profile.demo_profile_id,
            baseline_assessment_id=baseline.assessment_id,
            baseline_input_snapshot_id=baseline.input_snapshot_id,
            baseline_uncertainty=baseline.uncertainty,
            data_sources=baseline_snapshot.data_sources,
            accepted_evidence=accepted_evidence,
        )
        snapshot_json = json.dumps(
            snapshot.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
        snapshot_id = f"sas_{snapshot_hash}"

        try:
            result = self.adapter.run(snapshot)
        except Exception:
            result = AdapterAssessmentResult(
                status=AssessmentStatus.FAILED,
                reason_code="SUPPLEMENTAL_ASSESSMENT_ADAPTER_ERROR",
            )

        calculated_at = datetime.now(UTC)
        state = SupplementalAssessmentState(
            supplemental_assessment_id=f"sam_{uuid4().hex}",
            baseline_assessment_id=baseline.assessment_id,
            quality_check_id=quality.quality_check_id,
            submission_id=submission.submission_id,
            status=result.status,
            calculated_at=calculated_at,
            input_snapshot_id=snapshot_id,
            model_version=result.model_version,
            reason_code=result.reason_code,
            uncertainty=result.uncertainty,
        )
        output_summary: dict[str, str | bool] = {
            "supplementalAssessmentStatus": state.status.value,
            "baselineAssessmentId": baseline.assessment_id,
            "qualityCheckId": quality.quality_check_id,
            "evidenceType": submission.evidence_type,
            "demoOnly": state.demo_only,
        }
        if state.uncertainty is not None:
            output_summary.update(
                {
                    "calibrationMode": state.uncertainty.calibration_mode.value,
                    "calibrationVersion": state.uncertainty.calibration_version,
                }
            )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.SUPPLEMENTAL_ASSESSMENT_RUN,
            timestamp=calculated_at,
            actor=AuditActor.SYSTEM,
            input_version=quality.quality_check_id,
            input_snapshot_hash=snapshot_hash,
            output_summary=output_summary,
            data_version=submission.data_version,
            model_version=state.model_version,
            policy_version=quality.quality_policy_version,
        )
        saved = self.repository.save_supplemental_execution(
            session_id=session_id,
            state=state,
            snapshot=snapshot,
            audit_event=audit_event,
        )
        return SupplementalAssessmentResponse(
            session_id=session_id,
            supplemental_assessment=saved,
        )

    def readiness(self) -> dict[str, bool]:
        return {
            "supplemental_assessment_repository": self.repository.is_supplemental_ready(),
            "supplemental_assessment_adapter": self.adapter.is_ready(),
        }

    def _conflict(self, code: str, message: str) -> NoReturn:
        raise ResourceConflictError(code=code, message=message)


class AssessmentComparisonService:
    def __init__(
        self,
        repository: AssessmentRepository,
        session_service: CustomerSessionService,
    ) -> None:
        self.repository = repository
        self.session_service = session_service

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> AssessmentComparisonResponse:
        self.session_service.get_session(session_id)
        return AssessmentComparisonResponse(
            session_id=session_id,
            comparison=self.repository.get_latest_comparison(session_id),
        )

    def compare(self, session_id: str, request_id: str) -> AssessmentComparisonResponse:
        self.session_service.get_session(session_id)
        supplemental = self.repository.get_latest_supplemental(session_id)
        if supplemental is None:
            raise ResourceConflictError(
                code="SUPPLEMENTAL_ASSESSMENT_NOT_READY",
                message="평가 전후 비교 전에 보완평가가 필요합니다.",
            )
        existing = self.repository.get_comparison_by_supplemental_id(
            supplemental.supplemental_assessment_id
        )
        if existing is not None:
            return AssessmentComparisonResponse(session_id=session_id, comparison=existing)

        baseline = self.repository.get_for_session(
            session_id,
            supplemental.baseline_assessment_id,
        )
        if baseline is None:
            raise ResourceConflictError(
                code="BASELINE_ASSESSMENT_NOT_FOUND",
                message="보완평가와 연결된 기준평가를 확인할 수 없습니다.",
            )

        basis, change, rationale_codes = compare_uncertainties(
            baseline.uncertainty,
            supplemental.uncertainty,
        )
        input_snapshot = {
            "baseline": baseline.model_dump(mode="json", by_alias=True),
            "supplemental": supplemental.model_dump(mode="json", by_alias=True),
        }
        input_json = json.dumps(
            input_snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        input_snapshot_hash = hashlib.sha256(input_json.encode()).hexdigest()
        compared_at = datetime.now(UTC)
        state = AssessmentComparisonState(
            comparison_id=f"acp_{uuid4().hex}",
            baseline_assessment_id=baseline.assessment_id,
            supplemental_assessment_id=supplemental.supplemental_assessment_id,
            quality_check_id=supplemental.quality_check_id,
            basis=basis,
            uncertainty_change=change,
            before_uncertainty=baseline.uncertainty,
            after_uncertainty=supplemental.uncertainty,
            rationale_codes=rationale_codes,
            baseline_model_version=baseline.model_version,
            supplemental_model_version=supplemental.model_version,
            compared_at=compared_at,
        )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.ASSESSMENT_COMPARED,
            timestamp=compared_at,
            actor=AuditActor.SYSTEM,
            input_version=supplemental.supplemental_assessment_id,
            input_snapshot_hash=input_snapshot_hash,
            output_summary={
                "comparisonBasis": state.basis.value,
                "uncertaintyChange": state.uncertainty_change.value,
                "baselineAssessmentId": state.baseline_assessment_id,
                "supplementalAssessmentId": state.supplemental_assessment_id,
                "demoOnly": state.demo_only,
            },
            data_version=supplemental.input_snapshot_id,
            model_version=supplemental.model_version,
        )
        saved = self.repository.save_comparison(
            session_id=session_id,
            state=state,
            input_snapshot_hash=input_snapshot_hash,
            audit_event=audit_event,
        )
        return AssessmentComparisonResponse(session_id=session_id, comparison=saved)

    def readiness(self) -> dict[str, bool]:
        return {
            "assessment_comparison_repository": self.repository.is_comparison_ready(),
        }
