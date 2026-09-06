from app.repositories.assessment_review_repository import AssessmentReviewRepository
from app.repositories.evidence_quality_repository import EvidenceQualityRepository
from app.schemas.underwriter_review import (
    UnderwriterReviewQueueItem,
    UnderwriterReviewQueueResponse,
    UnderwriterReviewTriggerType,
)


class UnderwriterReviewQueueService:
    def __init__(
        self,
        *,
        quality_repository: EvidenceQualityRepository,
        assessment_review_repository: AssessmentReviewRepository,
    ) -> None:
        self.quality_repository = quality_repository
        self.assessment_review_repository = assessment_review_repository

    def list(self, *, limit: int, offset: int) -> UnderwriterReviewQueueResponse:
        fetch_limit = limit + offset
        qualities = self.quality_repository.list_review_required(
            limit=fetch_limit,
            offset=0,
        )
        requests = self.assessment_review_repository.list_latest(limit=fetch_limit)
        items = [
            UnderwriterReviewQueueItem(
                review_id=f"uwr_{quality.quality_check_id.removeprefix('evq_')}",
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
            for session_id, quality in qualities
        ]
        items.extend(
            UnderwriterReviewQueueItem(
                review_id=f"uwr_{review.review_request_id.removeprefix('arr_')}",
                session_id=session_id,
                trigger_type=UnderwriterReviewTriggerType.CUSTOMER_ASSESSMENT_REVIEW,
                trigger_id=review.review_request_id,
                target_type=review.target_type,
                target_assessment_id=review.target_assessment_id,
                reason_codes=[review.reason_code],
                requested_at=review.requested_at,
                data_version=review.data_version,
                policy_version=review.request_policy_version,
                demo_only=review.demo_only,
            )
            for session_id, review in requests
        )
        items.sort(key=lambda item: item.requested_at, reverse=True)
        total_count = (
            self.quality_repository.count_review_required()
            + self.assessment_review_repository.count()
        )
        return UnderwriterReviewQueueResponse(
            total_count=total_count,
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
        )
