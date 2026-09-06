import hashlib
import json
from datetime import UTC, datetime
from typing import NoReturn
from uuid import uuid4

from app.adapters.assessment_adapter import AssessmentAdapter, SupplementalAssessmentAdapter
from app.core.errors import EvidenceSubmissionNotFoundError, ResourceConflictError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.credit_history_repository import CreditHistoryRepository
from app.repositories.evidence_consent_repository import EvidenceConsentRepository
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
    AssessmentDataSnapshotReference,
    AssessmentInputSnapshot,
    AssessmentResponse,
    AssessmentSnapshotType,
    AssessmentState,
    AssessmentStatus,
    AssessmentUncertainty,
    AssessmentUncertaintyChange,
    ExistingAssessmentReference,
    SupplementalAssessmentInputSnapshot,
    SupplementalAssessmentResponse,
    SupplementalAssessmentState,
)
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.consent import ConsentStatus
from app.schemas.evidence_quality import EvidenceQualityStatus
from app.schemas.evidence_selection import EvidenceSelectionStatus
from app.schemas.evidence_submission import EvidenceSubmissionMode, EvidenceSubmissionState
from app.schemas.model_registry import ModelGovernanceResolution, ModelRole
from app.schemas.policy_boundary import BoundaryStatus
from app.services.assessment_data_lineage_service import AssessmentDataLineageService
from app.services.data_source_service import DataSourceService
from app.services.feature_snapshot_service import FeatureSnapshotService
from app.services.model_registry_service import ModelRegistryService
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
        data_lineage_service: AssessmentDataLineageService | None = None,
        feature_snapshot_service: FeatureSnapshotService | None = None,
        model_registry_service: ModelRegistryService | None = None,
        credit_history_repository: CreditHistoryRepository | None = None,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.data_source_service = data_source_service
        self.adapter = adapter
        self.data_lineage_service = data_lineage_service
        self.feature_snapshot_service = feature_snapshot_service
        self.model_registry_service = model_registry_service
        self.credit_history_repository = credit_history_repository

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> AssessmentResponse:
        self.session_service.get_session(session_id)
        state = self.repository.get_latest(session_id)
        if state is None:
            state = AssessmentState(status=AssessmentStatus.NOT_RUN)
        return AssessmentResponse(session_id=session_id, assessment=state)

    def run(self, session_id: str, request_id: str) -> AssessmentResponse:
        feature_cutoff_at = datetime.now(UTC)
        session = self.session_service.get_session(session_id).session
        data_sources = self.data_source_service.list_states(session_id).data_sources
        available_source_snapshots = (
            self.data_lineage_service.list_references(session_id)
            if self.data_lineage_service is not None
            else []
        )
        source_snapshots = [
            item
            for item in available_source_snapshots
            if item.observed_at <= feature_cutoff_at and item.loaded_at <= feature_cutoff_at
        ]
        excluded_source_snapshots = [
            item for item in available_source_snapshots if item not in source_snapshots
        ]
        feature_snapshot = (
            self.feature_snapshot_service.get_or_build(session_id, feature_cutoff_at)
            if self.feature_snapshot_service is not None and available_source_snapshots
            else None
        )
        source_assessment = self._resolve_source_assessment(
            session_id=session_id,
            feature_cutoff_at=feature_cutoff_at,
            source_snapshots=source_snapshots,
        )
        snapshot = AssessmentInputSnapshot(
            session_id=session_id,
            demo_profile_id=session.demo_profile.demo_profile_id,
            data_sources=data_sources,
            feature_cutoff_at=feature_cutoff_at,
            source_snapshots=source_snapshots,
            excluded_source_snapshots=excluded_source_snapshots,
            feature_snapshot=(
                self.feature_snapshot_service.get_reference(feature_snapshot)
                if self.feature_snapshot_service is not None and feature_snapshot is not None
                else None
            ),
            source_assessment=source_assessment,
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
        governance: ModelGovernanceResolution | None = None
        if self.model_registry_service is not None:
            result, governance = self.model_registry_service.govern(
                result,
                ModelRole.BASELINE_ASSESSMENT,
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
            source_assessment=source_assessment,
        )
        output_summary: dict[str, str | bool | int] = {
            "assessmentStatus": state.status.value,
            "featureCutoffApplied": True,
            "pointInTimeExcludedSourceCount": len(excluded_source_snapshots),
            "demoOnly": state.demo_only,
        }
        if state.uncertainty is not None:
            output_summary.update(
                {
                    "calibrationMode": state.uncertainty.calibration_mode.value,
                    "calibrationVersion": state.uncertainty.calibration_version,
                }
            )
        if source_assessment is not None:
            output_summary.update(
                {
                    "sourceCreditAssessmentId": source_assessment.credit_assessment_id,
                    "sourceAssessmentDataVersion": source_assessment.data_version,
                    "sourceAssessmentModelVersion": source_assessment.model_version,
                    "sourceAssessmentFeatureSetVersion": source_assessment.feature_set_version,
                    "sourceAssessmentPolicyVersion": source_assessment.policy_version,
                }
            )
        self._add_governance_summary(output_summary, governance)
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

    def _resolve_source_assessment(
        self,
        *,
        session_id: str,
        feature_cutoff_at: datetime,
        source_snapshots: list[AssessmentDataSnapshotReference],
    ) -> ExistingAssessmentReference | None:
        if self.credit_history_repository is None:
            return None
        credit_history_reference = next(
            (
                item
                for item in source_snapshots
                if item.snapshot_type == AssessmentSnapshotType.BANK_CREDIT_HISTORY
            ),
            None,
        )
        if credit_history_reference is None:
            return None
        credit_history = self.credit_history_repository.get_snapshot(session_id)
        if (
            credit_history is None
            or credit_history.data_version != credit_history_reference.data_version
        ):
            return None
        eligible = [
            item
            for item in credit_history.credit_assessments
            if item.assessed_at <= feature_cutoff_at and item.feature_cutoff_at <= feature_cutoff_at
        ]
        if not eligible:
            return None
        selected = max(
            eligible,
            key=lambda item: (item.assessed_at, item.credit_assessment_id),
        )
        return ExistingAssessmentReference(
            credit_assessment_id=selected.credit_assessment_id,
            data_version=credit_history.data_version,
            application_id=selected.application_id,
            assessment_type=selected.assessment_type,
            assessed_at=selected.assessed_at,
            feature_cutoff_at=selected.feature_cutoff_at,
            grade_code=selected.grade_code,
            grade_scale_version=selected.grade_scale_version,
            reason_codes=selected.reason_codes,
            model_version=selected.model_version,
            feature_set_version=selected.feature_set_version,
            policy_version=selected.policy_version,
        )

    def readiness(self) -> dict[str, bool]:
        return {
            "assessment_repository": self.repository.is_ready(),
            "assessment_adapter": self.adapter.is_ready(),
        }

    @staticmethod
    def _add_governance_summary(
        output_summary: dict[str, str | bool | int],
        governance: ModelGovernanceResolution | None,
    ) -> None:
        if governance is None:
            return
        output_summary.update(
            {
                "modelRegistryVersion": governance.registry_version,
                "modelGovernanceAllowed": governance.allowed,
                "requestedModelVersion": governance.requested_model_version,
            }
        )
        if governance.validation_status is not None:
            output_summary["modelValidationStatus"] = governance.validation_status.value
        if governance.operational_state is not None:
            output_summary["modelOperationalState"] = governance.operational_state.value
        if governance.feature_set_version is not None:
            output_summary["modelFeatureSetVersion"] = governance.feature_set_version
        if governance.training_data_version is not None:
            output_summary["modelTrainingDataVersion"] = governance.training_data_version
        if governance.policy_version is not None:
            output_summary["modelPolicyVersion"] = governance.policy_version


class SupplementalAssessmentService:
    def __init__(
        self,
        repository: AssessmentRepository,
        session_service: CustomerSessionService,
        quality_repository: EvidenceQualityRepository,
        submission_repository: EvidenceSubmissionRepository,
        evidence_consent_repository: EvidenceConsentRepository,
        selection_repository: EvidenceSelectionRepository,
        boundary_repository: PolicyBoundaryRepository,
        adapter: SupplementalAssessmentAdapter,
        model_registry_service: ModelRegistryService | None = None,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.quality_repository = quality_repository
        self.submission_repository = submission_repository
        self.evidence_consent_repository = evidence_consent_repository
        self.selection_repository = selection_repository
        self.boundary_repository = boundary_repository
        self.adapter = adapter
        self.model_registry_service = model_registry_service

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
        feature_cutoff_at = datetime.now(UTC)
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

        self._require_active_submission_consent(session_id, submission)

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

        accepted_evidence_set = self._accepted_evidence_set(
            session_id=session_id,
            boundary_check_id=boundary.boundary_check_id,
            current_submission_id=submission.submission_id,
            feature_cutoff_at=feature_cutoff_at,
        )
        accepted_evidence = accepted_evidence_set[-1]
        excluded_evidence_count = sum(
            item.point_in_time_valid is False for item in accepted_evidence_set
        )
        snapshot = SupplementalAssessmentInputSnapshot(
            session_id=session_id,
            demo_profile_id=session.demo_profile.demo_profile_id,
            baseline_assessment_id=baseline.assessment_id,
            baseline_input_snapshot_id=baseline.input_snapshot_id,
            baseline_uncertainty=baseline.uncertainty,
            baseline_source_assessment=baseline.source_assessment,
            feature_cutoff_at=feature_cutoff_at,
            data_sources=baseline_snapshot.data_sources,
            source_snapshots=baseline_snapshot.source_snapshots,
            feature_snapshot=baseline_snapshot.feature_snapshot,
            accepted_evidence=accepted_evidence,
            accepted_evidence_set=accepted_evidence_set,
        )
        snapshot_json = json.dumps(
            snapshot.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
        snapshot_id = f"sas_{snapshot_hash}"

        if excluded_evidence_count:
            result = AdapterAssessmentResult(
                status=AssessmentStatus.INSUFFICIENT_DATA,
                reason_code="EVIDENCE_AFTER_FEATURE_CUTOFF",
            )
        else:
            try:
                result = self.adapter.run(snapshot)
            except Exception:
                result = AdapterAssessmentResult(
                    status=AssessmentStatus.FAILED,
                    reason_code="SUPPLEMENTAL_ASSESSMENT_ADAPTER_ERROR",
                )
        governance: ModelGovernanceResolution | None = None
        if self.model_registry_service is not None:
            result, governance = self.model_registry_service.govern(
                result,
                ModelRole.SUPPLEMENTAL_ASSESSMENT,
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
            accepted_evidence_count=len(accepted_evidence_set),
        )
        output_summary: dict[str, str | bool | int] = {
            "supplementalAssessmentStatus": state.status.value,
            "baselineAssessmentId": baseline.assessment_id,
            "qualityCheckId": quality.quality_check_id,
            "evidenceType": submission.evidence_type,
            "acceptedEvidenceCount": state.accepted_evidence_count,
            "featureCutoffApplied": True,
            "pointInTimeExcludedEvidenceCount": excluded_evidence_count,
            "demoOnly": state.demo_only,
        }
        if state.uncertainty is not None:
            output_summary.update(
                {
                    "calibrationMode": state.uncertainty.calibration_mode.value,
                    "calibrationVersion": state.uncertainty.calibration_version,
                }
            )
        AssessmentService._add_governance_summary(output_summary, governance)
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

    def _accepted_evidence_set(
        self,
        *,
        session_id: str,
        boundary_check_id: str,
        current_submission_id: str,
        feature_cutoff_at: datetime,
    ) -> list[AcceptedEvidenceSnapshot]:
        qualities = {
            item.submission_id: item
            for item in self.quality_repository.list_for_session(session_id)
        }
        accepted: list[AcceptedEvidenceSnapshot] = []
        for submission in self.submission_repository.list_for_session(session_id):
            quality = qualities.get(submission.submission_id)
            if quality is None or (
                quality.status != EvidenceQualityStatus.ACCEPTED
                or not quality.eligible_for_reassessment
            ):
                continue
            selection = self.selection_repository.get_for_session(
                session_id,
                submission.selection_id,
            )
            if (
                quality.evidence_type != submission.evidence_type
                or quality.submission_snapshot_hash != submission.submission_snapshot_hash
                or quality.data_version != submission.data_version
                or selection is None
                or selection.status != EvidenceSelectionStatus.SELECTED
                or selection.selected_evidence is None
                or selection.selected_evidence.evidence_type != submission.evidence_type
                or selection.selected_evidence.source_type != submission.source_type
            ):
                self._conflict(
                    "ACCEPTED_EVIDENCE_LINEAGE_INVALID",
                    "누적 Evidence의 제출·품질·선택 이력이 일치하지 않습니다.",
                )
            if selection.boundary_check_id != boundary_check_id:
                continue
            self._require_active_submission_consent(session_id, submission)
            accepted.append(
                AcceptedEvidenceSnapshot(
                    quality_check_id=quality.quality_check_id,
                    submission_id=submission.submission_id,
                    selection_id=selection.selection_id,
                    boundary_check_id=selection.boundary_check_id,
                    resolution_id=selection.resolution_id,
                    evidence_type=submission.evidence_type,
                    source_type=submission.source_type,
                    observed_at=submission.observed_at,
                    submitted_at=submission.submitted_at,
                    checked_at=quality.checked_at,
                    point_in_time_valid=(
                        submission.observed_at <= feature_cutoff_at
                        and submission.submitted_at <= feature_cutoff_at
                        and quality.checked_at <= feature_cutoff_at
                    ),
                    submission_snapshot_hash=submission.submission_snapshot_hash,
                    evidence_data_version=submission.data_version,
                    quality_policy_version=quality.quality_policy_version,
                )
            )
        if not accepted or accepted[-1].submission_id != current_submission_id:
            self._conflict(
                "ACCEPTED_EVIDENCE_SET_NOT_READY",
                "현재 제출을 포함한 누적 Evidence 집합을 확인할 수 없습니다.",
            )
        return accepted

    def _require_active_submission_consent(
        self,
        session_id: str,
        submission: EvidenceSubmissionState,
    ) -> None:
        if submission.submission_mode != EvidenceSubmissionMode.DEMO_FILE_UPLOAD:
            return
        consent = self.evidence_consent_repository.get_for_selection(
            session_id,
            submission.selection_id,
        )
        if (
            consent is None
            or consent.status != ConsentStatus.GRANTED
            or consent.selection_id != submission.selection_id
            or consent.evidence_type != submission.evidence_type
            or consent.source_type != submission.source_type
            or submission.evidence_consent_id is None
            or consent.evidence_consent_id != submission.evidence_consent_id
            or submission.consent_scope_version is None
            or consent.scope_version != submission.consent_scope_version
        ):
            self._conflict(
                "EVIDENCE_CONSENT_NOT_ACTIVE",
                "현재 유효한 Evidence 동의가 있는 자료만 보완평가에 사용할 수 있습니다.",
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
