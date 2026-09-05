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

    @model_validator(mode="after")
    def validate_decision(self) -> "BoundaryDecision":
        if len(self.possible_routes) != len(set(self.possible_routes)):
            raise ValueError("possibleRoutes values must be unique")
        if len(self.crossed_boundary_codes) != len(set(self.crossed_boundary_codes)):
            raise ValueError("crossedBoundaryCodes values must be unique")
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
        elif not self.stop_reason or not self.underwriter_required:
            raise ValueError("POLICY_BLOCKED decision requires a stop reason and review")
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


class DemoPolicyBoundaryCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    grade_routes: list[DemoGradeRoute] = Field(min_length=1)
    boundaries: list[DemoRouteBoundary]
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
        return self
