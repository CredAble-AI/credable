from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn

from app.core.errors import ResourceConflictError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.evidence_quality_repository import EvidenceQualityRepository
from app.repositories.evidence_selection_repository import EvidenceSelectionRepository
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.repositories.policy_boundary_repository import PolicyBoundaryRepository
from app.schemas.consent import ConsentSourceType
from app.schemas.evidence_burden import (
    AdminEvidenceBurdenResponse,
    EvidenceTypeBurdenBreakdown,
)
from app.schemas.evidence_quality import (
    EvidenceQualityDimensionStatus,
    EvidenceQualityStatus,
)
from app.schemas.evidence_selection import EvidenceAvailability, EvidenceSelectionStatus
from app.services.session_service import CustomerSessionService


@dataclass
class _EvidenceTypeAccumulator:
    source_type: ConsentSourceType
    request_count: int
    submission_count: int
    accepted_count: int
    rejected_count: int
    review_required_count: int
    first_requested_at: datetime
    last_requested_at: datetime


class AdminEvidenceBurdenService:
    def __init__(
        self,
        *,
        session_service: CustomerSessionService,
        selection_repository: EvidenceSelectionRepository,
        submission_repository: EvidenceSubmissionRepository,
        quality_repository: EvidenceQualityRepository,
        assessment_repository: AssessmentRepository,
        resolution_repository: PolicyBoundaryRepository,
    ) -> None:
        self.session_service = session_service
        self.selection_repository = selection_repository
        self.submission_repository = submission_repository
        self.quality_repository = quality_repository
        self.assessment_repository = assessment_repository
        self.resolution_repository = resolution_repository

    def get(self, session_id: str) -> AdminEvidenceBurdenResponse:
        session = self.session_service.get_session(session_id).session
        selections = [
            item
            for item in self.selection_repository.list_for_session(session_id)
            if item.status == EvidenceSelectionStatus.SELECTED
            and item.selected_evidence is not None
        ]
        submissions = self.submission_repository.list_for_session(session_id)
        qualities = self.quality_repository.list_for_session(session_id)
        latest_supplemental = self.assessment_repository.get_latest_supplemental(session_id)
        latest_resolution = self.resolution_repository.get_latest_resolution(session_id)

        as_of_candidates = [session.created_at]
        as_of_candidates.extend(item.selected_at for item in selections)
        as_of_candidates.extend(item.submitted_at for item in submissions)
        as_of_candidates.extend(item.checked_at for item in qualities)
        if latest_supplemental is not None:
            as_of_candidates.append(latest_supplemental.calculated_at)
        if latest_resolution is not None:
            as_of_candidates.append(latest_resolution.resolved_at)

        selection_by_id = {item.selection_id: item for item in selections}
        breakdowns: dict[str, _EvidenceTypeAccumulator] = {}
        availability_counts = {availability: 0 for availability in EvidenceAvailability}
        for selection in selections:
            selected = selection.selected_evidence
            if selected is None:
                continue
            availability_counts[selected.availability] += 1
            existing = breakdowns.get(selected.evidence_type)
            if existing is None:
                breakdowns[selected.evidence_type] = _EvidenceTypeAccumulator(
                    source_type=selected.source_type,
                    request_count=1,
                    submission_count=0,
                    accepted_count=0,
                    rejected_count=0,
                    review_required_count=0,
                    first_requested_at=selection.selected_at,
                    last_requested_at=selection.selected_at,
                )
            else:
                if existing.source_type != selected.source_type:
                    self._invalid_lineage()
                existing.request_count += 1
                existing.last_requested_at = selection.selected_at

        submission_by_id = {}
        submitted_selection_ids: set[str] = set()
        for submission in submissions:
            selection = selection_by_id.get(submission.selection_id)
            if (
                selection is None
                or selection.selected_evidence is None
                or selection.selected_evidence.evidence_type != submission.evidence_type
                or selection.selected_evidence.source_type != submission.source_type
                or submission.selection_id in submitted_selection_ids
            ):
                self._invalid_lineage()
            breakdown = breakdowns[submission.evidence_type]
            breakdown.submission_count += 1
            submitted_selection_ids.add(submission.selection_id)
            submission_by_id[submission.submission_id] = submission

        checked_submission_ids: set[str] = set()
        failed_quality_dimension_count = 0
        accepted_count = 0
        rejected_count = 0
        review_required_count = 0
        for quality in qualities:
            submission = submission_by_id.get(quality.submission_id)
            if (
                submission is None
                or quality.evidence_type != submission.evidence_type
                or quality.submission_snapshot_hash != submission.submission_snapshot_hash
                or quality.data_version != submission.data_version
                or quality.submission_id in checked_submission_ids
            ):
                self._invalid_lineage()
            breakdown = breakdowns[quality.evidence_type]
            if quality.status == EvidenceQualityStatus.ACCEPTED:
                accepted_count += 1
                breakdown.accepted_count += 1
            elif quality.status == EvidenceQualityStatus.REVIEW_REQUIRED:
                review_required_count += 1
                breakdown.review_required_count += 1
            else:
                rejected_count += 1
                breakdown.rejected_count += 1
            failed_quality_dimension_count += sum(
                item.status != EvidenceQualityDimensionStatus.PASSED for item in quality.checks
            )
            checked_submission_ids.add(quality.submission_id)

        evidence_types = [
            EvidenceTypeBurdenBreakdown(
                evidence_type=evidence_type,
                source_type=item.source_type,
                request_count=item.request_count,
                submission_count=item.submission_count,
                accepted_count=item.accepted_count,
                rejected_count=item.rejected_count,
                review_required_count=item.review_required_count,
                first_requested_at=item.first_requested_at,
                last_requested_at=item.last_requested_at,
            )
            for evidence_type, item in sorted(
                breakdowns.items(),
                key=lambda pair: (pair[1].first_requested_at, pair[0]),
            )
        ]
        request_count = len(selections)
        submission_count = len(submissions)
        resolution_count = self.resolution_repository.count_resolutions(session_id)
        return AdminEvidenceBurdenResponse(
            session_id=session_id,
            as_of=max(as_of_candidates),
            evidence_request_count=request_count,
            repeated_request_count=sum(item.iteration > 1 for item in selections),
            available_request_count=availability_counts[EvidenceAvailability.AVAILABLE],
            requestable_request_count=availability_counts[EvidenceAvailability.REQUESTABLE],
            consent_required_request_count=availability_counts[
                EvidenceAvailability.CONSENT_REQUIRED
            ],
            unavailable_request_count=availability_counts[EvidenceAvailability.UNAVAILABLE],
            submission_count=submission_count,
            pending_submission_count=request_count - submission_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            review_required_count=review_required_count,
            unverified_submission_count=submission_count - len(qualities),
            failed_quality_dimension_count=failed_quality_dimension_count,
            supplemental_assessment_count=(
                self.assessment_repository.count_supplemental_executions(session_id)
            ),
            resolution_count=resolution_count,
            latest_resolution_status=(
                latest_resolution.status if latest_resolution is not None else None
            ),
            collection_stopped=(
                latest_resolution.stop_evidence_collection
                if latest_resolution is not None
                else None
            ),
            max_request_iteration=max((item.iteration for item in selections), default=0),
            evidence_types=evidence_types,
            demo_only=session.demo_only,
        )

    @staticmethod
    def _invalid_lineage() -> NoReturn:
        raise ResourceConflictError(
            code="EVIDENCE_BURDEN_LINEAGE_INVALID",
            message="Evidence 부담 지표를 계산할 수 있도록 연결된 이력이 필요합니다.",
        )
