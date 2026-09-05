from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from uuid import uuid4

from app.core.errors import ResourceConflictError
from app.repositories.policy_boundary_repository import PolicyBoundaryRepository
from app.schemas.assessment import AssessmentStatus, AssessmentUncertainty
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.policy_boundary import (
    BoundaryDecision,
    BoundaryStatus,
    DemoPolicyBoundaryCatalogData,
    PolicyBoundaryCheckResponse,
    PolicyBoundaryCheckState,
)
from app.services.assessment_service import AssessmentService
from app.services.session_service import CustomerSessionService


class DemoPolicyBoundaryCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoPolicyBoundaryCatalogData | None = None
        self._routes_by_grade: dict[str, str] = {}
        self._codes_by_route_pair: dict[frozenset[str], str] = {}

    @property
    def policy_version(self) -> str:
        return self._load().policy_version

    def evaluate(self, uncertainty: AssessmentUncertainty) -> BoundaryDecision:
        self._load()
        if not uncertainty.grade_set:
            return self._blocked("DEMO_NUMERIC_POLICY_BOUNDARY_NOT_CONFIGURED")

        routes: list[str] = []
        for grade in uncertainty.grade_set:
            route = self._routes_by_grade.get(grade)
            if route is None:
                return self._blocked("DEMO_GRADE_POLICY_NOT_CONFIGURED")
            if route not in routes:
                routes.append(route)

        if len(routes) == 1:
            return BoundaryDecision(
                status=BoundaryStatus.STABLE,
                possible_routes=routes,
                crossed_boundary_codes=[],
                stop_reason="PATH_STABLE",
                underwriter_required=False,
            )

        crossed_codes: list[str] = []
        for left_route, right_route in combinations(routes, 2):
            code = self._codes_by_route_pair.get(frozenset((left_route, right_route)))
            if code is None:
                return self._blocked("DEMO_ROUTE_BOUNDARY_NOT_CONFIGURED")
            crossed_codes.append(code)
        return BoundaryDecision(
            status=BoundaryStatus.AMBIGUOUS,
            possible_routes=routes,
            crossed_boundary_codes=crossed_codes,
            stop_reason=None,
            underwriter_required=False,
        )

    def is_ready(self) -> bool:
        try:
            self._load()
        except (OSError, ValueError):
            return False
        return True

    def _blocked(self, reason: str) -> BoundaryDecision:
        return BoundaryDecision(
            status=BoundaryStatus.POLICY_BLOCKED,
            possible_routes=[],
            crossed_boundary_codes=[],
            stop_reason=reason,
            underwriter_required=True,
        )

    def _load(self) -> DemoPolicyBoundaryCatalogData:
        if self._catalog is None:
            self._catalog = DemoPolicyBoundaryCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
            self._routes_by_grade = {item.grade: item.route for item in self._catalog.grade_routes}
            self._codes_by_route_pair = {
                frozenset((item.left_route, item.right_route)): item.boundary_code
                for item in self._catalog.boundaries
            }
        return self._catalog


class PolicyBoundaryService:
    def __init__(
        self,
        repository: PolicyBoundaryRepository,
        session_service: CustomerSessionService,
        assessment_service: AssessmentService,
        catalog: DemoPolicyBoundaryCatalog,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.assessment_service = assessment_service
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> PolicyBoundaryCheckResponse:
        self.session_service.get_session(session_id)
        return PolicyBoundaryCheckResponse(
            session_id=session_id,
            boundary_check=self.repository.get_latest(session_id),
        )

    def check(self, session_id: str, request_id: str) -> PolicyBoundaryCheckResponse:
        self.session_service.get_session(session_id)
        assessment = self.assessment_service.get_latest(session_id).assessment
        if (
            assessment.status != AssessmentStatus.COMPLETED
            or assessment.assessment_id is None
            or assessment.input_snapshot_id is None
            or assessment.uncertainty is None
        ):
            raise ResourceConflictError(
                code="ASSESSMENT_NOT_READY_FOR_BOUNDARY_CHECK",
                message="완료된 기준평가와 불확실성 결과가 필요합니다.",
            )

        checked_at = datetime.now(UTC)
        decision = self.catalog.evaluate(assessment.uncertainty)
        state = PolicyBoundaryCheckState(
            boundary_check_id=f"pbc_{uuid4().hex}",
            assessment_id=assessment.assessment_id,
            checked_at=checked_at,
            decision=decision,
            input_snapshot_id=assessment.input_snapshot_id,
            calibration_version=assessment.uncertainty.calibration_version,
            policy_version=self.catalog.policy_version,
        )
        output_summary: dict[str, str | bool | int] = {
            "boundaryStatus": decision.status.value,
            "possibleRouteCount": len(decision.possible_routes),
            "crossedBoundaryCount": len(decision.crossed_boundary_codes),
            "underwriterRequired": decision.underwriter_required,
            "demoOnly": state.demo_only,
        }
        if decision.stop_reason is not None:
            output_summary["stopReason"] = decision.stop_reason
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.POLICY_BOUNDARY_CHECKED,
            timestamp=checked_at,
            actor=AuditActor.SYSTEM,
            input_version=assessment.assessment_id,
            input_snapshot_hash=assessment.input_snapshot_id.removeprefix("dss_"),
            output_summary=output_summary,
            data_version=assessment.input_snapshot_id,
            model_version=assessment.model_version,
            policy_version=state.policy_version,
        )
        saved = self.repository.save_check(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return PolicyBoundaryCheckResponse(session_id=session_id, boundary_check=saved)

    def readiness(self) -> dict[str, bool]:
        return {
            "policy_boundary_repository": self.repository.is_ready(),
            "policy_boundary_catalog": self.catalog.is_ready(),
        }
