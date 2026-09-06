import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from uuid import uuid4

from app.core.errors import ResourceConflictError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.policy_boundary_repository import PolicyBoundaryRepository
from app.schemas.assessment import (
    AssessmentComparisonBasis,
    AssessmentStatus,
    AssessmentUncertainty,
)
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.policy_boundary import (
    BoundaryDecision,
    BoundaryStatus,
    DemoPolicyBoundaryCatalogData,
    DemoPolicyRestriction,
    EvidenceResolutionNextAction,
    EvidenceResolutionResponse,
    EvidenceResolutionState,
    EvidenceResolutionStatus,
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
        self._restrictions_by_reason: dict[str, DemoPolicyRestriction] = {}

    @property
    def policy_version(self) -> str:
        return self._load().policy_version

    def evaluate(
        self,
        uncertainty: AssessmentUncertainty,
        restriction_reason_codes: Sequence[str] = (),
    ) -> BoundaryDecision:
        self._load()
        restriction = self._restriction_for(restriction_reason_codes)
        if restriction is not None:
            return BoundaryDecision(
                status=BoundaryStatus.POLICY_BLOCKED,
                possible_routes=[],
                crossed_boundary_codes=[],
                stop_reason=restriction.restriction_code,
                underwriter_required=False,
                restriction_code=restriction.restriction_code,
                follow_up_codes=list(restriction.follow_up_codes),
            )
        if not uncertainty.grade_set:
            return self._undecided("DEMO_NUMERIC_POLICY_BOUNDARY_NOT_CONFIGURED")

        routes: list[str] = []
        for grade in uncertainty.grade_set:
            route = self._routes_by_grade.get(grade)
            if route is None:
                return self._undecided("DEMO_GRADE_POLICY_NOT_CONFIGURED")
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
                return self._undecided("DEMO_ROUTE_BOUNDARY_NOT_CONFIGURED")
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

    def _restriction_for(
        self,
        restriction_reason_codes: Sequence[str],
    ) -> DemoPolicyRestriction | None:
        for reason_code in restriction_reason_codes:
            restriction = self._restrictions_by_reason.get(reason_code)
            if restriction is not None:
                return restriction
        return None

    def _undecided(self, reason: str) -> BoundaryDecision:
        """The catalog cannot place this result, so an underwriter decides."""
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
            self._restrictions_by_reason = {
                reason_code: restriction
                for restriction in self._catalog.policy_restrictions
                for reason_code in restriction.trigger_reason_codes
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
        decision = self.catalog.evaluate(
            assessment.uncertainty,
            (
                assessment.source_assessment.reason_codes
                if assessment.source_assessment is not None
                else ()
            ),
        )
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
        if decision.restriction_code is not None:
            output_summary["policyRestrictionCode"] = decision.restriction_code
            output_summary["followUpCount"] = len(decision.follow_up_codes)
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


class EvidenceResolutionService:
    def __init__(
        self,
        repository: PolicyBoundaryRepository,
        assessment_repository: AssessmentRepository,
        session_service: CustomerSessionService,
        catalog: DemoPolicyBoundaryCatalog,
    ) -> None:
        self.repository = repository
        self.assessment_repository = assessment_repository
        self.session_service = session_service
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> EvidenceResolutionResponse:
        self.session_service.get_session(session_id)
        return EvidenceResolutionResponse(
            session_id=session_id,
            resolution=self.repository.get_latest_resolution(session_id),
        )

    def resolve(self, session_id: str, request_id: str) -> EvidenceResolutionResponse:
        self.session_service.get_session(session_id)
        comparison = self.assessment_repository.get_latest_comparison(session_id)
        if comparison is None:
            raise ResourceConflictError(
                code="ASSESSMENT_COMPARISON_NOT_READY",
                message="Evidence 수집 종료 판단 전에 평가 전후 비교가 필요합니다.",
            )
        existing = self.repository.get_resolution_by_comparison_id(comparison.comparison_id)
        if existing is not None:
            return EvidenceResolutionResponse(session_id=session_id, resolution=existing)

        supplemental = self.assessment_repository.get_latest_supplemental(session_id)
        if (
            supplemental is None
            or supplemental.supplemental_assessment_id != comparison.supplemental_assessment_id
        ):
            raise ResourceConflictError(
                code="ASSESSMENT_COMPARISON_LINEAGE_NOT_READY",
                message="현재 보완평가와 연결된 비교 이력이 필요합니다.",
            )

        if (
            comparison.basis == AssessmentComparisonBasis.NOT_COMPARABLE
            or comparison.after_uncertainty is None
        ):
            state = self._human_review_state(
                comparison_id=comparison.comparison_id,
                supplemental_assessment_id=supplemental.supplemental_assessment_id,
                reason_code="UNCERTAINTY_COMPARISON_NOT_RELIABLE",
                calibration_version=(
                    comparison.after_uncertainty.calibration_version
                    if comparison.after_uncertainty is not None
                    else None
                ),
            )
        else:
            decision = self.catalog.evaluate(comparison.after_uncertainty)
            state = self._state_from_boundary(
                comparison_id=comparison.comparison_id,
                supplemental_assessment_id=supplemental.supplemental_assessment_id,
                decision=decision,
                calibration_version=comparison.after_uncertainty.calibration_version,
            )

        comparison_json = json.dumps(
            comparison.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.EVIDENCE_COLLECTION_RESOLVED,
            timestamp=state.resolved_at,
            actor=AuditActor.SYSTEM,
            input_version=comparison.comparison_id,
            input_snapshot_hash=hashlib.sha256(comparison_json.encode()).hexdigest(),
            output_summary={
                "resolutionStatus": state.status.value,
                "nextAction": state.next_action.value,
                "stopEvidenceCollection": state.stop_evidence_collection,
                "underwriterRequired": state.underwriter_required,
                "reasonCode": state.reason_code,
                "demoOnly": state.demo_only,
            },
            data_version=supplemental.input_snapshot_id,
            model_version=supplemental.model_version,
            policy_version=state.boundary_policy_version,
        )
        saved = self.repository.save_resolution(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return EvidenceResolutionResponse(session_id=session_id, resolution=saved)

    def _state_from_boundary(
        self,
        *,
        comparison_id: str,
        supplemental_assessment_id: str,
        decision: BoundaryDecision,
        calibration_version: str,
    ) -> EvidenceResolutionState:
        common = {
            "resolution_id": f"res_{uuid4().hex}",
            "comparison_id": comparison_id,
            "supplemental_assessment_id": supplemental_assessment_id,
            "possible_routes": decision.possible_routes,
            "crossed_boundary_codes": decision.crossed_boundary_codes,
            "resolved_at": datetime.now(UTC),
            "calibration_version": calibration_version,
            "boundary_policy_version": self.catalog.policy_version,
        }
        if decision.status == BoundaryStatus.STABLE:
            return EvidenceResolutionState(
                **common,
                status=EvidenceResolutionStatus.RESOLVED,
                next_action=EvidenceResolutionNextAction.SHOW_UPDATED_RESULTS,
                stop_evidence_collection=True,
                underwriter_required=False,
                reason_code="PATH_STABLE",
            )
        if decision.status == BoundaryStatus.AMBIGUOUS:
            return EvidenceResolutionState(
                **common,
                status=EvidenceResolutionStatus.MORE_EVIDENCE_REQUIRED,
                next_action=EvidenceResolutionNextAction.REQUEST_NEXT_EVIDENCE,
                stop_evidence_collection=False,
                underwriter_required=False,
                reason_code="POLICY_BOUNDARY_STILL_AMBIGUOUS",
            )
        return EvidenceResolutionState(
            **common,
            status=EvidenceResolutionStatus.HUMAN_REVIEW,
            next_action=EvidenceResolutionNextAction.UNDERWRITER_REVIEW,
            stop_evidence_collection=True,
            underwriter_required=True,
            reason_code=decision.stop_reason or "POLICY_BLOCKED",
        )

    def _human_review_state(
        self,
        *,
        comparison_id: str,
        supplemental_assessment_id: str,
        reason_code: str,
        calibration_version: str | None,
    ) -> EvidenceResolutionState:
        return EvidenceResolutionState(
            resolution_id=f"res_{uuid4().hex}",
            comparison_id=comparison_id,
            supplemental_assessment_id=supplemental_assessment_id,
            status=EvidenceResolutionStatus.HUMAN_REVIEW,
            next_action=EvidenceResolutionNextAction.UNDERWRITER_REVIEW,
            stop_evidence_collection=True,
            underwriter_required=True,
            reason_code=reason_code,
            possible_routes=[],
            crossed_boundary_codes=[],
            resolved_at=datetime.now(UTC),
            calibration_version=calibration_version,
            boundary_policy_version=self.catalog.policy_version,
        )

    def readiness(self) -> dict[str, bool]:
        return {
            "evidence_resolution_repository": self.repository.is_resolution_ready(),
        }
