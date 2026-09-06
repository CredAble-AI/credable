from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import NoReturn
from uuid import uuid4

from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.assessment_review_repository import AssessmentReviewRepository
from app.repositories.evidence_quality_repository import EvidenceQualityRepository
from app.repositories.evidence_selection_repository import EvidenceSelectionRepository
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.repositories.policy_boundary_repository import PolicyBoundaryRepository
from app.repositories.underwriter_review_repository import UnderwriterReviewRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.evidence_quality import EvidenceQualityState, EvidenceQualityStatus
from app.schemas.evidence_selection import EvidenceSelectionState, EvidenceSelectionStatus
from app.schemas.evidence_submission import EvidenceSubmissionState
from app.schemas.policy_boundary import (
    BoundaryStatus,
    EvidenceResolutionState,
    EvidenceResolutionStatus,
    PolicyBoundaryCheckState,
)
from app.schemas.review_workflow import (
    UnderwriterReviewResultCode,
    UnderwriterReviewStatus,
    UnderwriterReviewWorkflowState,
)
from app.schemas.underwriter_review import (
    UnderwriterReviewCaseContext,
    UnderwriterReviewDetailResponse,
    UnderwriterReviewQueueItem,
    UnderwriterReviewQueueResponse,
    UnderwriterReviewTriggerType,
)

_EVIDENCE_RESULTS = {
    UnderwriterReviewResultCode.EVIDENCE_CONFIRMED,
    UnderwriterReviewResultCode.EVIDENCE_EXCLUDED,
    UnderwriterReviewResultCode.ADDITIONAL_INFORMATION_REQUIRED,
    UnderwriterReviewResultCode.ESCALATED,
}
_ASSESSMENT_RESULTS = {
    UnderwriterReviewResultCode.ASSESSMENT_CONFIRMED,
    UnderwriterReviewResultCode.CORRECTION_REQUIRED,
    UnderwriterReviewResultCode.ADDITIONAL_INFORMATION_REQUIRED,
    UnderwriterReviewResultCode.ESCALATED,
}


class UnderwriterReviewQueueService:
    def __init__(
        self,
        *,
        quality_repository: EvidenceQualityRepository,
        assessment_repository: AssessmentRepository,
        assessment_review_repository: AssessmentReviewRepository,
        evidence_selection_repository: EvidenceSelectionRepository,
        submission_repository: EvidenceSubmissionRepository,
        boundary_repository: PolicyBoundaryRepository,
        workflow_repository: UnderwriterReviewRepository,
    ) -> None:
        self.quality_repository = quality_repository
        self.assessment_repository = assessment_repository
        self.assessment_review_repository = assessment_review_repository
        self.evidence_selection_repository = evidence_selection_repository
        self.submission_repository = submission_repository
        self.boundary_repository = boundary_repository
        self.workflow_repository = workflow_repository

    def initialize(self) -> None:
        self.workflow_repository.initialize()

    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: UnderwriterReviewStatus | None,
    ) -> UnderwriterReviewQueueResponse:
        items = [self._apply_workflow(item) for item in self._all_source_items()]
        if status is not None:
            items = [item for item in items if item.status == status]
        items.sort(key=lambda item: item.requested_at, reverse=True)
        return UnderwriterReviewQueueResponse(
            total_count=len(items),
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
        )

    def get(self, review_id: str) -> UnderwriterReviewDetailResponse:
        return self._detail(self._source_item(review_id))

    def claim(self, review_id: str, request_id: str) -> UnderwriterReviewDetailResponse:
        source = self._source_item(review_id)
        existing = self.workflow_repository.get(review_id)
        if existing is not None:
            self._require_matching_lineage(source, existing)
            if existing.status == UnderwriterReviewStatus.COMPLETED:
                raise ResourceConflictError(
                    code="UNDERWRITER_REVIEW_ALREADY_COMPLETED",
                    message="이미 완료된 심사역 검토는 다시 접수할 수 없습니다.",
                )
            return self._detail(source)

        started_at = datetime.now(UTC)
        state = UnderwriterReviewWorkflowState(
            review_id=source.review_id,
            session_id=source.session_id,
            trigger_type=source.trigger_type.value,
            trigger_id=source.trigger_id,
            status=UnderwriterReviewStatus.IN_REVIEW,
            reviewer_principal="demo-underwriter",
            started_at=started_at,
        )
        saved = self.workflow_repository.save_started(
            state=state,
            audit_event=self._audit_event(
                source=source,
                state=state,
                request_id=request_id,
                stage=AuditStage.UNDERWRITER_REVIEW_STARTED,
            ),
        )
        self._require_matching_lineage(source, saved)
        return self._detail(source)

    def complete(
        self,
        review_id: str,
        result_code: UnderwriterReviewResultCode,
        request_id: str,
    ) -> UnderwriterReviewDetailResponse:
        source = self._source_item(review_id)
        self._require_allowed_result(source.trigger_type, result_code)
        existing = self.workflow_repository.get(review_id)
        if existing is None:
            raise ResourceConflictError(
                code="UNDERWRITER_REVIEW_NOT_CLAIMED",
                message="심사역 검토를 먼저 접수해야 완료할 수 있습니다.",
            )
        self._require_matching_lineage(source, existing)
        if existing.status == UnderwriterReviewStatus.COMPLETED:
            if existing.result_code == result_code:
                return self._detail(source)
            raise ResourceConflictError(
                code="UNDERWRITER_REVIEW_RESULT_CONFLICT",
                message="완료된 심사역 검토 결과는 변경할 수 없습니다.",
            )

        completed_at = datetime.now(UTC)
        state = UnderwriterReviewWorkflowState.model_validate(
            existing.model_copy(
                update={
                    "status": UnderwriterReviewStatus.COMPLETED,
                    "result_code": result_code,
                    "completed_at": completed_at,
                }
            ).model_dump()
        )
        saved = self.workflow_repository.save_completed(
            state=state,
            audit_event=self._audit_event(
                source=source,
                state=state,
                request_id=request_id,
                stage=AuditStage.UNDERWRITER_REVIEW_COMPLETED,
            ),
        )
        if saved.status == UnderwriterReviewStatus.COMPLETED and saved.result_code != result_code:
            raise ResourceConflictError(
                code="UNDERWRITER_REVIEW_RESULT_CONFLICT",
                message="완료된 심사역 검토 결과는 변경할 수 없습니다.",
            )
        return self._detail(source)

    def readiness(self) -> dict[str, bool]:
        return {"underwriter_review_repository": self.workflow_repository.is_ready()}

    def _detail(self, source: UnderwriterReviewQueueItem) -> UnderwriterReviewDetailResponse:
        return UnderwriterReviewDetailResponse(
            review=self._apply_workflow(source),
            context=self._case_context(source),
        )

    def _case_context(self, source: UnderwriterReviewQueueItem) -> UnderwriterReviewCaseContext:
        assessment = None
        boundary = None
        selection = None
        submission = None
        quality = None
        supplemental = None
        comparison = None
        resolution = None

        if source.trigger_type == UnderwriterReviewTriggerType.CUSTOMER_ASSESSMENT_REVIEW:
            if source.target_type is None or source.target_assessment_id is None:
                raise ValueError("customer review target lineage is missing")
            if source.target_type.value == "BASELINE_ASSESSMENT":
                assessment = self.assessment_repository.get_for_session(
                    source.session_id,
                    source.target_assessment_id,
                )
            else:
                supplemental = self.assessment_repository.get_supplemental_for_session(
                    source.session_id,
                    source.target_assessment_id,
                )
                if supplemental is not None:
                    comparison = self.assessment_repository.get_comparison_by_supplemental_id(
                        supplemental.supplemental_assessment_id
                    )
                    quality = self._quality_for_id(source.session_id, supplemental.quality_check_id)
                    submission = self._submission_for_quality(source.session_id, quality)
                    assessment = self.assessment_repository.get_for_session(
                        source.session_id,
                        supplemental.baseline_assessment_id,
                    )
                    if submission is not None:
                        selection = self.evidence_selection_repository.get_for_session(
                            source.session_id,
                            submission.selection_id,
                        )
                    if selection is not None:
                        boundary = self._boundary_for_id(
                            source.session_id,
                            selection.boundary_check_id,
                        )

        elif source.trigger_type == UnderwriterReviewTriggerType.EVIDENCE_QUALITY:
            quality = self._quality_for_id(source.session_id, source.trigger_id)
            submission = self._submission_for_quality(source.session_id, quality)
            if submission is not None:
                selection = self.evidence_selection_repository.get_for_session(
                    source.session_id,
                    submission.selection_id,
                )
            if selection is not None:
                boundary = self._boundary_for_id(source.session_id, selection.boundary_check_id)
            if boundary is not None:
                assessment = self.assessment_repository.get_for_session(
                    source.session_id,
                    boundary.assessment_id,
                )

        elif source.trigger_type == UnderwriterReviewTriggerType.POLICY_BOUNDARY:
            boundary = self._boundary_for_id(source.session_id, source.trigger_id)
            if boundary is not None:
                assessment = self.assessment_repository.get_for_session(
                    source.session_id,
                    boundary.assessment_id,
                )

        elif source.trigger_type == UnderwriterReviewTriggerType.EVIDENCE_SELECTION:
            selection_record = self.evidence_selection_repository.get_by_selection_id(
                source.trigger_id
            )
            if selection_record is not None and selection_record[0] == source.session_id:
                selection = selection_record[1]
                boundary = self._boundary_for_id(source.session_id, selection.boundary_check_id)
            if boundary is not None:
                assessment = self.assessment_repository.get_for_session(
                    source.session_id,
                    boundary.assessment_id,
                )

        elif source.trigger_type == UnderwriterReviewTriggerType.EVIDENCE_RESOLUTION:
            resolution_record = self.boundary_repository.get_resolution_by_id(source.trigger_id)
            if resolution_record is not None and resolution_record[0] == source.session_id:
                resolution = resolution_record[1]
                supplemental = self.assessment_repository.get_supplemental_for_session(
                    source.session_id,
                    resolution.supplemental_assessment_id,
                )
                comparison = self.assessment_repository.get_comparison_by_supplemental_id(
                    resolution.supplemental_assessment_id
                )
            if supplemental is not None:
                quality = self._quality_for_id(source.session_id, supplemental.quality_check_id)
                submission = self._submission_for_quality(source.session_id, quality)
                assessment = self.assessment_repository.get_for_session(
                    source.session_id,
                    supplemental.baseline_assessment_id,
                )
                if submission is not None:
                    selection = self.evidence_selection_repository.get_for_session(
                        source.session_id,
                        submission.selection_id,
                    )
                if selection is not None:
                    boundary = self._boundary_for_id(
                        source.session_id,
                        selection.boundary_check_id,
                    )

        return UnderwriterReviewCaseContext(
            assessment=assessment,
            boundary_check=boundary,
            selection=selection,
            submission=submission,
            quality=quality,
            supplemental_assessment=supplemental,
            comparison=comparison,
            resolution=resolution,
        )

    def _quality_for_id(
        self, session_id: str, quality_check_id: str
    ) -> EvidenceQualityState | None:
        record = self.quality_repository.get_by_quality_check_id(quality_check_id)
        if record is None or record[0] != session_id:
            return None
        return record[1]

    def _submission_for_quality(
        self,
        session_id: str,
        quality: EvidenceQualityState | None,
    ) -> EvidenceSubmissionState | None:
        if quality is None:
            return None
        return self.submission_repository.get_for_session(session_id, quality.submission_id)

    def _boundary_for_id(
        self,
        session_id: str,
        boundary_check_id: str,
    ) -> PolicyBoundaryCheckState | None:
        record = self.boundary_repository.get_check_by_id(boundary_check_id)
        if record is None or record[0] != session_id:
            return None
        return record[1]

    def _all_source_items(self) -> list[UnderwriterReviewQueueItem]:
        quality_count = self.quality_repository.count_review_required()
        request_count = self.assessment_review_repository.count()
        qualities = self.quality_repository.list_review_required(
            limit=max(quality_count, 1),
            offset=0,
        )
        requests = self.assessment_review_repository.list_latest(limit=max(request_count, 1))
        boundaries = self.boundary_repository.list_policy_blocked()
        selections = self.evidence_selection_repository.list_human_review_required()
        resolutions = self.boundary_repository.list_human_review_resolutions()
        return [
            *[self._quality_item(session_id, quality) for session_id, quality in qualities],
            *[self._assessment_item(session_id, review) for session_id, review in requests],
            *[self._boundary_item(session_id, boundary) for session_id, boundary in boundaries],
            *[self._selection_item(session_id, selection) for session_id, selection in selections],
            *[
                self._resolution_item(session_id, resolution)
                for session_id, resolution in resolutions
            ],
        ]

    def _source_item(self, review_id: str) -> UnderwriterReviewQueueItem:
        if not review_id.startswith("uwr_") or len(review_id) <= 4:
            self._not_found(review_id)
        suffix = review_id.removeprefix("uwr_")
        quality_record = self.quality_repository.get_by_quality_check_id(f"evq_{suffix}")
        request_record = self.assessment_review_repository.get_by_id(f"arr_{suffix}")
        boundary_record = self.boundary_repository.get_check_by_id(f"pbc_{suffix}")
        selection_record = self.evidence_selection_repository.get_by_selection_id(f"evs_{suffix}")
        resolution_record = self.boundary_repository.get_resolution_by_id(f"res_{suffix}")
        candidates: list[UnderwriterReviewQueueItem] = []
        if quality_record is not None:
            session_id, quality = quality_record
            if quality.status == EvidenceQualityStatus.REVIEW_REQUIRED:
                candidates.append(self._quality_item(session_id, quality))
        if request_record is not None:
            session_id, review = request_record
            candidates.append(self._assessment_item(session_id, review))
        if boundary_record is not None:
            session_id, boundary = boundary_record
            if (
                boundary.decision.status == BoundaryStatus.POLICY_BLOCKED
                and boundary.decision.underwriter_required
            ):
                candidates.append(self._boundary_item(session_id, boundary))
        if selection_record is not None:
            session_id, selection = selection_record
            if (
                selection.status == EvidenceSelectionStatus.HUMAN_REVIEW
                and selection.underwriter_required
            ):
                candidates.append(self._selection_item(session_id, selection))
        if resolution_record is not None:
            session_id, resolution = resolution_record
            if (
                resolution.status == EvidenceResolutionStatus.HUMAN_REVIEW
                and resolution.underwriter_required
            ):
                candidates.append(self._resolution_item(session_id, resolution))
        if not candidates:
            self._not_found(review_id)
        if len(candidates) != 1:
            raise ValueError("reviewId collision requires manual data repair")
        return candidates[0]

    def _apply_workflow(self, item: UnderwriterReviewQueueItem) -> UnderwriterReviewQueueItem:
        state = self.workflow_repository.get(item.review_id)
        if state is None:
            return item
        self._require_matching_lineage(item, state)
        return UnderwriterReviewQueueItem.model_validate(
            item.model_copy(
                update={
                    "status": state.status,
                    "result_code": state.result_code,
                    "started_at": state.started_at,
                    "completed_at": state.completed_at,
                }
            ).model_dump()
        )

    @staticmethod
    def _quality_item(
        session_id: str,
        quality: EvidenceQualityState,
    ) -> UnderwriterReviewQueueItem:
        return UnderwriterReviewQueueItem(
            review_id=UnderwriterReviewQueueService._review_id(quality.quality_check_id),
            session_id=session_id,
            trigger_type=UnderwriterReviewTriggerType.EVIDENCE_QUALITY,
            trigger_id=quality.quality_check_id,
            evidence_type=quality.evidence_type,
            reason_codes=quality.suspicion_codes,
            requested_at=quality.checked_at,
            data_version=quality.data_version,
            policy_version=quality.quality_policy_version,
            demo_only=quality.demo_only,
        )

    @staticmethod
    def _assessment_item(session_id: str, review) -> UnderwriterReviewQueueItem:
        return UnderwriterReviewQueueItem(
            review_id=UnderwriterReviewQueueService._review_id(review.review_request_id),
            session_id=session_id,
            trigger_type=UnderwriterReviewTriggerType.CUSTOMER_ASSESSMENT_REVIEW,
            trigger_id=review.review_request_id,
            target_type=review.target_type,
            target_assessment_id=review.target_assessment_id,
            reason_codes=[
                code
                for code in (review.reason_code, review.customer_reason_code)
                if code is not None
            ],
            requested_at=review.requested_at,
            data_version=review.data_version,
            policy_version=review.request_policy_version,
            demo_only=review.demo_only,
        )

    @staticmethod
    def _boundary_item(
        session_id: str,
        boundary: PolicyBoundaryCheckState,
    ) -> UnderwriterReviewQueueItem:
        if boundary.decision.stop_reason is None:
            raise ValueError("policy-blocked boundary requires a stop reason")
        return UnderwriterReviewQueueItem(
            review_id=UnderwriterReviewQueueService._review_id(boundary.boundary_check_id),
            session_id=session_id,
            trigger_type=UnderwriterReviewTriggerType.POLICY_BOUNDARY,
            trigger_id=boundary.boundary_check_id,
            reason_codes=[boundary.decision.stop_reason],
            requested_at=boundary.checked_at,
            data_version=boundary.input_snapshot_id,
            policy_version=boundary.policy_version,
            demo_only=boundary.demo_only,
        )

    def _selection_item(
        self,
        session_id: str,
        selection: EvidenceSelectionState,
    ) -> UnderwriterReviewQueueItem:
        if selection.stop_reason is None:
            raise ValueError("human-review selection requires a stop reason")
        boundary_record = self.boundary_repository.get_check_by_id(selection.boundary_check_id)
        if boundary_record is None or boundary_record[0] != session_id:
            raise ValueError("Evidence selection boundary lineage is inconsistent")
        return UnderwriterReviewQueueItem(
            review_id=UnderwriterReviewQueueService._review_id(selection.selection_id),
            session_id=session_id,
            trigger_type=UnderwriterReviewTriggerType.EVIDENCE_SELECTION,
            trigger_id=selection.selection_id,
            reason_codes=[selection.stop_reason],
            requested_at=selection.selected_at,
            data_version=boundary_record[1].input_snapshot_id,
            policy_version=selection.selection_policy_version,
            demo_only=selection.demo_only,
        )

    @staticmethod
    def _resolution_item(
        session_id: str,
        resolution: EvidenceResolutionState,
    ) -> UnderwriterReviewQueueItem:
        return UnderwriterReviewQueueItem(
            review_id=UnderwriterReviewQueueService._review_id(resolution.resolution_id),
            session_id=session_id,
            trigger_type=UnderwriterReviewTriggerType.EVIDENCE_RESOLUTION,
            trigger_id=resolution.resolution_id,
            reason_codes=[resolution.reason_code],
            requested_at=resolution.resolved_at,
            data_version=resolution.supplemental_assessment_id,
            policy_version=resolution.boundary_policy_version,
            demo_only=resolution.demo_only,
        )

    @staticmethod
    def _review_id(trigger_id: str) -> str:
        return f"uwr_{trigger_id.split('_', maxsplit=1)[-1]}"

    @staticmethod
    def _require_allowed_result(
        trigger_type: UnderwriterReviewTriggerType,
        result_code: UnderwriterReviewResultCode,
    ) -> None:
        allowed = (
            _EVIDENCE_RESULTS
            if trigger_type == UnderwriterReviewTriggerType.EVIDENCE_QUALITY
            else _ASSESSMENT_RESULTS
        )
        if result_code not in allowed:
            raise ResourceConflictError(
                code="UNDERWRITER_REVIEW_RESULT_NOT_ALLOWED",
                message="검토 Trigger 유형에 사용할 수 없는 처리 결과입니다.",
            )

    @staticmethod
    def _require_matching_lineage(
        source: UnderwriterReviewQueueItem,
        state: UnderwriterReviewWorkflowState,
    ) -> None:
        if (
            state.review_id != source.review_id
            or state.session_id != source.session_id
            or state.trigger_type != source.trigger_type.value
            or state.trigger_id != source.trigger_id
        ):
            raise ValueError("review Workflow lineage is inconsistent")

    @staticmethod
    def _audit_event(
        *,
        source: UnderwriterReviewQueueItem,
        state: UnderwriterReviewWorkflowState,
        request_id: str,
        stage: AuditStage,
    ) -> SessionAuditEvent:
        snapshot = source.model_dump(mode="json", by_alias=True, exclude_none=True)
        serialized = json.dumps(snapshot, separators=(",", ":"), sort_keys=True)
        snapshot_hash = hashlib.sha256(serialized.encode()).hexdigest()
        output_summary: dict[str, str | bool | int | float] = {
            "reviewId": state.review_id,
            "reviewStatus": state.status.value,
            "triggerType": state.trigger_type,
            "demoOnly": state.demo_only,
        }
        if state.result_code is not None:
            output_summary["resultCode"] = state.result_code.value
        return SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=source.session_id,
            request_id=request_id,
            stage=stage,
            timestamp=state.completed_at or state.started_at or datetime.now(UTC),
            actor=AuditActor.UNDERWRITER,
            input_version=source.trigger_id,
            input_snapshot_hash=snapshot_hash,
            output_summary=output_summary,
            data_version=source.data_version,
            policy_version=state.workflow_policy_version,
        )

    @staticmethod
    def _not_found(review_id: str) -> NoReturn:
        raise ResourceNotFoundError(
            code="UNDERWRITER_REVIEW_NOT_FOUND",
            message=f"심사역 검토 대상을 찾을 수 없습니다: {review_id}",
        )
