import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.core.errors import ResourceConflictError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.assessment_review_repository import AssessmentReviewRepository
from app.repositories.underwriter_review_repository import UnderwriterReviewRepository
from app.schemas.assessment import AssessmentStatus
from app.schemas.assessment_review import (
    AssessmentReviewRequestResponse,
    AssessmentReviewRequestState,
    AssessmentReviewTargetType,
)
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.review_workflow import CustomerReviewProcessing, UnderwriterReviewStatus
from app.services.session_service import CustomerSessionService


class AssessmentReviewRequestService:
    def __init__(
        self,
        *,
        repository: AssessmentReviewRepository,
        assessment_repository: AssessmentRepository,
        session_service: CustomerSessionService,
        workflow_repository: UnderwriterReviewRepository,
    ) -> None:
        self.repository = repository
        self.assessment_repository = assessment_repository
        self.session_service = session_service
        self.workflow_repository = workflow_repository

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> AssessmentReviewRequestResponse:
        self.session_service.get_session(session_id)
        return self._response(session_id, self.repository.get_latest(session_id))

    def request(self, session_id: str, request_id: str) -> AssessmentReviewRequestResponse:
        session = self.session_service.get_session(session_id).session
        supplemental = self.assessment_repository.get_latest_supplemental(session_id)
        baseline = self.assessment_repository.get_latest(session_id)
        if supplemental is not None and supplemental.status == AssessmentStatus.COMPLETED:
            target_type = AssessmentReviewTargetType.SUPPLEMENTAL_ASSESSMENT
            target_id = supplemental.supplemental_assessment_id
            model_version = supplemental.model_version
        elif baseline is not None and baseline.status == AssessmentStatus.COMPLETED:
            target_type = AssessmentReviewTargetType.BASELINE_ASSESSMENT
            target_id = baseline.assessment_id
            model_version = baseline.model_version
        else:
            raise ResourceConflictError(
                code="ASSESSMENT_REVIEW_TARGET_NOT_READY",
                message="완료된 평가 결과가 있어야 재확인을 요청할 수 있습니다.",
            )
        if target_id is None or model_version is None:
            raise ValueError("completed review target requires identifiers and modelVersion")

        existing = self.repository.get_for_target(session_id, target_id)
        if existing is not None:
            return self._response(session_id, existing)

        requested_at = datetime.now(UTC)
        snapshot = {
            "sessionId": session_id,
            "targetType": target_type.value,
            "targetAssessmentId": target_id,
            "dataVersion": session.data_version,
            "modelVersion": model_version,
            "requestPolicyVersion": "assessment-review-request-policy-v1",
        }
        serialized = json.dumps(snapshot, separators=(",", ":"), sort_keys=True)
        snapshot_hash = hashlib.sha256(serialized.encode()).hexdigest()
        state = AssessmentReviewRequestState(
            review_request_id=f"arr_{uuid4().hex}",
            target_type=target_type,
            target_assessment_id=target_id,
            requested_at=requested_at,
            request_snapshot_hash=snapshot_hash,
            data_version=session.data_version,
            model_version=model_version,
        )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.ASSESSMENT_REVIEW_REQUESTED,
            timestamp=requested_at,
            actor=AuditActor.CUSTOMER,
            input_version=target_id,
            input_snapshot_hash=snapshot_hash,
            output_summary={
                "reviewRequestId": state.review_request_id,
                "targetType": state.target_type.value,
                "reasonCode": state.reason_code,
                "demoOnly": state.demo_only,
            },
            data_version=state.data_version,
            model_version=state.model_version,
            policy_version=state.request_policy_version,
        )
        saved = self.repository.save(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return self._response(session_id, saved)

    def readiness(self) -> dict[str, bool]:
        return {"assessment_review_repository": self.repository.is_ready()}

    def _response(
        self,
        session_id: str,
        review: AssessmentReviewRequestState | None,
    ) -> AssessmentReviewRequestResponse:
        if review is None:
            return AssessmentReviewRequestResponse(
                session_id=session_id,
                review_request=None,
            )
        underwriter_review_id = f"uwr_{review.review_request_id.removeprefix('arr_')}"
        workflow = self.workflow_repository.get(underwriter_review_id)
        processing = (
            CustomerReviewProcessing(status=UnderwriterReviewStatus.PENDING)
            if workflow is None
            else CustomerReviewProcessing(
                status=workflow.status,
                result_code=workflow.result_code,
                started_at=workflow.started_at,
                completed_at=workflow.completed_at,
            )
        )
        return AssessmentReviewRequestResponse(
            session_id=session_id,
            review_request=review,
            underwriter_review_id=underwriter_review_id,
            processing=processing,
        )
