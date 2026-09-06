from app.repositories.evidence_quality_repository import EvidenceQualityRepository
from app.schemas.underwriter_review import (
    UnderwriterReviewQueueItem,
    UnderwriterReviewQueueResponse,
    UnderwriterReviewTriggerType,
)


class UnderwriterReviewQueueService:
    def __init__(self, quality_repository: EvidenceQualityRepository) -> None:
        self.quality_repository = quality_repository

    def list(self, *, limit: int, offset: int) -> UnderwriterReviewQueueResponse:
        qualities = self.quality_repository.list_review_required(
            limit=limit,
            offset=offset,
        )
        return UnderwriterReviewQueueResponse(
            total_count=self.quality_repository.count_review_required(),
            limit=limit,
            offset=offset,
            items=[
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
            ],
        )
