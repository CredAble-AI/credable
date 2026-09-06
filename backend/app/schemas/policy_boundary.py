from datetime import datetime
from enum import StrEnum
from itertools import combinations
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class BoundaryStatus(StrEnum):
    STABLE = "STABLE"
    AMBIGUOUS = "AMBIGUOUS"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class BoundaryDecision(ApiModel):
    status: BoundaryStatus
    possible_routes: list[str]
    crossed_boundary_codes: list[str]
    stop_reason: str | None = None
    underwriter_required: bool
    restriction_code: str | None = Field(default=None, min_length=1)
    follow_up_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_decision(self) -> "BoundaryDecision":
        if len(self.possible_routes) != len(set(self.possible_routes)):
            raise ValueError("possibleRoutes values must be unique")
        if len(self.crossed_boundary_codes) != len(set(self.crossed_boundary_codes)):
            raise ValueError("crossedBoundaryCodes values must be unique")
        if len(self.follow_up_codes) != len(set(self.follow_up_codes)):
            raise ValueError("followUpCodes values must be unique")
        if self.status == BoundaryStatus.STABLE:
            if len(self.possible_routes) != 1:
                raise ValueError("STABLE decision requires one possible route")
            if self.crossed_boundary_codes:
                raise ValueError("STABLE decision cannot cross a policy boundary")
            if self.stop_reason != "PATH_STABLE" or self.underwriter_required:
                raise ValueError("STABLE decision must stop without underwriter review")
        elif self.status == BoundaryStatus.AMBIGUOUS:
            if len(self.possible_routes) < 2 or not self.crossed_boundary_codes:
                raise ValueError("AMBIGUOUS decision requires multiple routes and a boundary")
            if self.stop_reason is not None or self.underwriter_required:
                raise ValueError("AMBIGUOUS decision must continue to evidence acquisition")
        elif not self.stop_reason:
            raise ValueError("POLICY_BLOCKED decision requires a stop reason")
        elif self.restriction_code is not None:
            # A confirmed lending-policy restriction: the outcome is already
            # decided, so the customer gets the reason and the next steps
            # instead of being queued for an underwriter.
            if self.restriction_code != self.stop_reason:
                raise ValueError("policy restriction must be the stop reason")
            if not self.follow_up_codes:
                raise ValueError("policy restriction requires follow-up guidance")
            if self.underwriter_required:
                raise ValueError("confirmed policy restriction is not an underwriter handoff")
        elif not self.underwriter_required or self.follow_up_codes:
            # No restriction identified means the service could not decide,
            # which always goes to an underwriter.
            raise ValueError("undecided POLICY_BLOCKED decision requires underwriter review")
        return self


class PolicyBoundaryCheckState(ApiModel):
    boundary_check_id: str = Field(min_length=1)
    assessment_id: str = Field(min_length=1)
    checked_at: datetime
    decision: BoundaryDecision
    input_snapshot_id: str = Field(min_length=1)
    calibration_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_checked_at(self) -> "PolicyBoundaryCheckState":
        if self.checked_at.tzinfo is None:
            raise ValueError("checkedAt must include a timezone")
        return self


class PolicyBoundaryCheckResponse(ApiModel):
    session_id: str = Field(min_length=1)
    boundary_check: PolicyBoundaryCheckState | None


class EvidenceResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class EvidenceResolutionNextAction(StrEnum):
    SHOW_UPDATED_RESULTS = "SHOW_UPDATED_RESULTS"
    REQUEST_NEXT_EVIDENCE = "REQUEST_NEXT_EVIDENCE"
    UNDERWRITER_REVIEW = "UNDERWRITER_REVIEW"


class EvidenceResolutionState(ApiModel):
    resolution_id: str = Field(min_length=1)
    comparison_id: str = Field(min_length=1)
    supplemental_assessment_id: str = Field(min_length=1)
    status: EvidenceResolutionStatus
    next_action: EvidenceResolutionNextAction
    stop_evidence_collection: bool
    underwriter_required: bool
    reason_code: str = Field(min_length=1)
    possible_routes: list[str]
    crossed_boundary_codes: list[str]
    resolved_at: datetime
    calibration_version: str | None
    boundary_policy_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_resolution(self) -> "EvidenceResolutionState":
        if self.resolved_at.tzinfo is None:
            raise ValueError("resolvedAt must include a timezone")
        if len(self.possible_routes) != len(set(self.possible_routes)):
            raise ValueError("possibleRoutes values must be unique")
        if len(self.crossed_boundary_codes) != len(set(self.crossed_boundary_codes)):
            raise ValueError("crossedBoundaryCodes values must be unique")
        if self.status == EvidenceResolutionStatus.RESOLVED:
            if (
                self.next_action != EvidenceResolutionNextAction.SHOW_UPDATED_RESULTS
                or not self.stop_evidence_collection
                or self.underwriter_required
                or len(self.possible_routes) != 1
                or self.crossed_boundary_codes
            ):
                raise ValueError("RESOLVED state requires one stable route")
        elif self.status == EvidenceResolutionStatus.MORE_EVIDENCE_REQUIRED:
            if (
                self.next_action != EvidenceResolutionNextAction.REQUEST_NEXT_EVIDENCE
                or self.stop_evidence_collection
                or self.underwriter_required
                or len(self.possible_routes) < 2
                or not self.crossed_boundary_codes
            ):
                raise ValueError("MORE_EVIDENCE_REQUIRED state must continue collection")
        elif (
            self.next_action != EvidenceResolutionNextAction.UNDERWRITER_REVIEW
            or not self.stop_evidence_collection
            or not self.underwriter_required
        ):
            raise ValueError("HUMAN_REVIEW state must stop automated collection")
        return self


class EvidenceResolutionResponse(ApiModel):
    session_id: str = Field(min_length=1)
    resolution: EvidenceResolutionState | None


class DemoGradeRoute(ApiModel):
    grade: str = Field(min_length=1)
    route: str = Field(min_length=1)


class DemoRouteBoundary(ApiModel):
    left_route: str = Field(min_length=1)
    right_route: str = Field(min_length=1)
    boundary_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_distinct_routes(self) -> "DemoRouteBoundary":
        if self.left_route == self.right_route:
            raise ValueError("route boundary requires two distinct routes")
        return self


class DemoPolicyRestriction(ApiModel):
    """A lending-policy limit that additional evidence cannot resolve."""

    restriction_code: str = Field(min_length=1)
    trigger_reason_codes: list[str] = Field(min_length=1)
    follow_up_codes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_codes(self) -> "DemoPolicyRestriction":
        if len(self.trigger_reason_codes) != len(set(self.trigger_reason_codes)):
            raise ValueError("triggerReasonCodes values must be unique")
        if len(self.follow_up_codes) != len(set(self.follow_up_codes)):
            raise ValueError("followUpCodes values must be unique")
        return self


class DemoPolicyBoundaryCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    grade_routes: list[DemoGradeRoute] = Field(min_length=1)
    boundaries: list[DemoRouteBoundary]
    policy_restrictions: list[DemoPolicyRestriction] = Field(default_factory=list)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_catalog(self) -> "DemoPolicyBoundaryCatalogData":
        grades = [item.grade for item in self.grade_routes]
        if len(grades) != len(set(grades)):
            raise ValueError("gradeRoutes grade values must be unique")
        routes = {item.route for item in self.grade_routes}
        pairs: set[frozenset[str]] = set()
        for boundary in self.boundaries:
            if boundary.left_route not in routes or boundary.right_route not in routes:
                raise ValueError("boundary routes must exist in gradeRoutes")
            pair = frozenset((boundary.left_route, boundary.right_route))
            if pair in pairs:
                raise ValueError("route boundary pairs must be unique")
            pairs.add(pair)
        configured_routes = sorted(routes)
        required_pairs = {frozenset(pair) for pair in combinations(configured_routes, 2)}
        if pairs != required_pairs:
            raise ValueError("every configured route pair requires one boundary code")
        restriction_codes = [item.restriction_code for item in self.policy_restrictions]
        if len(restriction_codes) != len(set(restriction_codes)):
            raise ValueError("policyRestrictions restrictionCode values must be unique")
        return self
