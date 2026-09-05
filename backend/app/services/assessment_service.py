import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.adapters.assessment_adapter import AssessmentAdapter
from app.repositories.assessment_repository import AssessmentRepository
from app.schemas.assessment import (
    AdapterAssessmentResult,
    AssessmentInputSnapshot,
    AssessmentResponse,
    AssessmentState,
    AssessmentStatus,
)
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.services.data_source_service import DataSourceService
from app.services.session_service import CustomerSessionService


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
