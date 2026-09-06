import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.adapters.explanation_adapter import ExplanationProvider
from app.core.errors import ResourceConflictError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.explanation_repository import AssessmentExplanationRepository
from app.repositories.policy_boundary_repository import PolicyBoundaryRepository
from app.schemas.assessment import AssessmentStatus, AssessmentUncertaintyChange
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.explanation import (
    AssessmentExplanationInputSnapshot,
    AssessmentExplanationResponse,
    AssessmentExplanationState,
    ExplanationFact,
    ExplanationPlan,
    ExplanationRenderingMode,
    ExplanationSection,
    ExplanationSourceReference,
    ExplanationSourceType,
    ExplanationTargetType,
)
from app.schemas.policy_boundary import BoundaryStatus, EvidenceResolutionStatus
from app.services.session_service import CustomerSessionService


@dataclass(frozen=True)
class _AllowedMessage:
    code: str
    title: str
    text: str
    source_reference_ids: tuple[str, ...]


class AssessmentExplanationService:
    POLICY_VERSION = "assessment-explanation-policy-v1"
    FALLBACK_PROVIDER_VERSION = "rule-explanation-fallback-v1"
    FALLBACK_PROMPT_VERSION = "not-applicable-v1"
    CAUTION_TEXT = (
        "이 설명은 서버가 확정한 구조화 결과를 요약한 것으로 대출 승인·부결, "
        "금리 또는 한도를 의미하지 않습니다. 최종 금융 판단은 심사역이 수행합니다."
    )

    def __init__(
        self,
        *,
        repository: AssessmentExplanationRepository,
        session_service: CustomerSessionService,
        assessment_repository: AssessmentRepository,
        boundary_repository: PolicyBoundaryRepository,
        provider: ExplanationProvider,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.assessment_repository = assessment_repository
        self.boundary_repository = boundary_repository
        self.provider = provider

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> AssessmentExplanationResponse:
        session = self.session_service.get_session(session_id).session
        explanation = self.repository.get_latest(session_id)
        if explanation is not None:
            try:
                snapshot, _ = self._build_snapshot_and_messages(
                    session_id,
                    session.data_version,
                )
            except ResourceConflictError:
                explanation = None
            else:
                if explanation.input_snapshot_hash != self._snapshot_hash(snapshot):
                    explanation = None
        return AssessmentExplanationResponse(
            session_id=session_id,
            explanation=explanation,
        )

    def generate(self, session_id: str, request_id: str) -> AssessmentExplanationResponse:
        session = self.session_service.get_session(session_id).session
        snapshot, messages = self._build_snapshot_and_messages(session_id, session.data_version)
        snapshot_hash = self._snapshot_hash(snapshot)
        existing = self.repository.get_by_input_snapshot_hash(session_id, snapshot_hash)
        if existing is not None:
            return AssessmentExplanationResponse(session_id=session_id, explanation=existing)

        allowed_codes = tuple(message.code for message in messages)
        fallback_reason_code: str | None = None
        try:
            plan = self.provider.plan(snapshot, allowed_codes)
            self._validate_provider_plan(plan, allowed_codes)
            self._validate_provider_metadata()
            rendering_mode = self.provider.rendering_mode
            provider_version = self.provider.provider_version
            model_version = self.provider.model_version
            prompt_version = self.provider.prompt_version
        except ValueError:
            plan = self._fallback_plan(allowed_codes)
            fallback_reason_code = "EXPLANATION_PROVIDER_OUTPUT_INVALID"
            rendering_mode = ExplanationRenderingMode.RULE_FALLBACK
            provider_version = self.FALLBACK_PROVIDER_VERSION
            model_version = None
            prompt_version = self.FALLBACK_PROMPT_VERSION
        except Exception:
            plan = self._fallback_plan(allowed_codes)
            fallback_reason_code = "EXPLANATION_PROVIDER_ERROR"
            rendering_mode = ExplanationRenderingMode.RULE_FALLBACK
            provider_version = self.FALLBACK_PROVIDER_VERSION
            model_version = None
            prompt_version = self.FALLBACK_PROMPT_VERSION

        message_by_code = {message.code: message for message in messages}
        selected = [message_by_code[code] for code in plan.section_codes]
        generated_at = datetime.now(UTC)
        state = AssessmentExplanationState(
            explanation_id=f"exp_{uuid4().hex}",
            target_type=snapshot.target_type,
            target_assessment_id=snapshot.target_assessment_id,
            headline=message_by_code[plan.headline_code].title,
            sections=[
                ExplanationSection(
                    message_code=message.code,
                    title=message.title,
                    text=message.text,
                    source_reference_ids=list(message.source_reference_ids),
                )
                for message in selected
            ],
            caution_text=self.CAUTION_TEXT,
            source_references=snapshot.source_references,
            input_snapshot_hash=snapshot_hash,
            rendering_mode=rendering_mode,
            fallback_applied=fallback_reason_code is not None,
            fallback_reason_code=fallback_reason_code,
            provider_version=provider_version,
            model_version=model_version,
            prompt_version=prompt_version,
            explanation_policy_version=self.POLICY_VERSION,
            data_version=session.data_version,
            generated_at=generated_at,
        )
        output_summary: dict[str, str | bool | int | float] = {
            "explanationId": state.explanation_id,
            "targetType": state.target_type.value,
            "renderingMode": state.rendering_mode.value,
            "fallbackApplied": state.fallback_applied,
            "demoOnly": state.demo_only,
        }
        if state.fallback_reason_code is not None:
            output_summary["fallbackReasonCode"] = state.fallback_reason_code
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.ASSESSMENT_EXPLANATION_GENERATED,
            timestamp=generated_at,
            actor=AuditActor.SYSTEM,
            input_version=state.target_assessment_id,
            input_snapshot_hash=snapshot_hash,
            output_summary=output_summary,
            data_version=state.data_version,
            model_version=state.model_version,
            policy_version=state.explanation_policy_version,
        )
        saved = self.repository.save(
            session_id=session_id,
            state=state,
            snapshot=snapshot,
            audit_event=audit_event,
        )
        return AssessmentExplanationResponse(session_id=session_id, explanation=saved)

    def readiness(self) -> dict[str, bool]:
        try:
            self._validate_provider_metadata()
            provider_ready = True
        except ValueError:
            provider_ready = False
        return {
            "assessment_explanation_repository": self.repository.is_ready(),
            "assessment_explanation_provider": provider_ready,
        }

    def _build_snapshot_and_messages(
        self,
        session_id: str,
        data_version: str,
    ) -> tuple[AssessmentExplanationInputSnapshot, list[_AllowedMessage]]:
        baseline = self.assessment_repository.get_latest(session_id)
        if baseline is None or baseline.status == AssessmentStatus.NOT_RUN:
            raise ResourceConflictError(
                code="ASSESSMENT_EXPLANATION_TARGET_NOT_READY",
                message="실행된 기준평가가 있어야 결과 설명을 생성할 수 있습니다.",
            )
        if baseline.assessment_id is None:
            raise ValueError("executed baseline assessment requires assessmentId")

        facts: list[ExplanationFact] = []
        sources: list[ExplanationSourceReference] = []
        messages: list[_AllowedMessage] = []
        self._add_source(
            sources,
            ExplanationSourceType.BASELINE_ASSESSMENT,
            baseline.assessment_id,
            data_version,
            baseline.model_version,
            baseline.source_assessment.policy_version if baseline.source_assessment else None,
        )
        self._add_fact(facts, "BASELINE_STATUS", baseline.assessment_id, baseline.status.value)
        if baseline.reason_code:
            self._add_fact(
                facts,
                "BASELINE_REASON_CODE",
                baseline.assessment_id,
                baseline.reason_code,
            )
        if baseline.uncertainty and baseline.uncertainty.grade_set:
            self._add_fact(
                facts,
                "BASELINE_GRADE_SET",
                baseline.assessment_id,
                *baseline.uncertainty.grade_set,
            )
        baseline_message = (
            _AllowedMessage(
                "BASELINE_RESULT_AVAILABLE",
                "기준평가 결과가 확인됐습니다",
                "서버에 저장된 기준평가 상태와 결과 범위를 기준으로 설명합니다.",
                (baseline.assessment_id,),
            )
            if baseline.status == AssessmentStatus.COMPLETED
            else _AllowedMessage(
                "BASELINE_RESULT_INCOMPLETE",
                "기준평가가 완료되지 않았습니다",
                "서버가 제공한 상태와 사유 코드를 확인해야 하며 결과를 임의로 보완하지 않습니다.",
                (baseline.assessment_id,),
            )
        )
        messages.append(baseline_message)
        if baseline.uncertainty and len(baseline.uncertainty.grade_set) > 1:
            messages.append(
                _AllowedMessage(
                    "BASELINE_UNCERTAINTY_PRESENT",
                    "결과 범위가 하나로 확정되지 않았습니다",
                    "기준평가에 복수의 등급 후보가 남아 있어 정책 경계 확인이 필요합니다.",
                    (baseline.assessment_id,),
                )
            )

        boundary = self.boundary_repository.get_latest(session_id)
        if boundary is not None and boundary.assessment_id == baseline.assessment_id:
            self._add_source(
                sources,
                ExplanationSourceType.POLICY_BOUNDARY,
                boundary.boundary_check_id,
                data_version,
                None,
                boundary.policy_version,
            )
            self._add_fact(
                facts,
                "BOUNDARY_STATUS",
                boundary.boundary_check_id,
                boundary.decision.status.value,
            )
            if boundary.decision.possible_routes:
                self._add_fact(
                    facts,
                    "BOUNDARY_POSSIBLE_ROUTES",
                    boundary.boundary_check_id,
                    *boundary.decision.possible_routes,
                )
            if boundary.decision.crossed_boundary_codes:
                self._add_fact(
                    facts,
                    "BOUNDARY_CODES",
                    boundary.boundary_check_id,
                    *boundary.decision.crossed_boundary_codes,
                )
            if boundary.decision.stop_reason:
                self._add_fact(
                    facts,
                    "BOUNDARY_STOP_REASON",
                    boundary.boundary_check_id,
                    boundary.decision.stop_reason,
                )
            boundary_copy = {
                BoundaryStatus.STABLE: (
                    "POLICY_PATH_STABLE",
                    "하나의 정책 경로가 확인됐습니다",
                    "현재 평가 범위가 하나의 정책 경로에 속해 추가 증빙을 요청하지 않습니다.",
                ),
                BoundaryStatus.AMBIGUOUS: (
                    "POLICY_PATH_AMBIGUOUS",
                    "정책 경계에 불확실성이 남아 있습니다",
                    "현재 평가 범위가 둘 이상의 정책 경로에 걸쳐 최소 증빙 확인이 필요합니다.",
                ),
                BoundaryStatus.POLICY_BLOCKED: (
                    "POLICY_REVIEW_REQUIRED",
                    "심사역 확인이 필요한 상태입니다",
                    "정책 매핑만으로 경계를 확정할 수 없어 자동 판단하지 않고 심사역에게 이관합니다.",
                ),
            }[boundary.decision.status]
            messages.append(_AllowedMessage(*boundary_copy, (boundary.boundary_check_id,)))

        supplemental = self.assessment_repository.get_latest_supplemental(session_id)
        if (
            supplemental is not None
            and supplemental.baseline_assessment_id != baseline.assessment_id
        ):
            supplemental = None
        comparison = None
        resolution = None
        target_type = ExplanationTargetType.BASELINE_ASSESSMENT
        target_assessment_id = baseline.assessment_id
        if supplemental is not None:
            target_type = ExplanationTargetType.SUPPLEMENTAL_ASSESSMENT
            target_assessment_id = supplemental.supplemental_assessment_id
            self._add_source(
                sources,
                ExplanationSourceType.SUPPLEMENTAL_ASSESSMENT,
                supplemental.supplemental_assessment_id,
                data_version,
                supplemental.model_version,
                None,
            )
            self._add_fact(
                facts,
                "SUPPLEMENTAL_STATUS",
                supplemental.supplemental_assessment_id,
                supplemental.status.value,
            )
            if supplemental.reason_code:
                self._add_fact(
                    facts,
                    "SUPPLEMENTAL_REASON_CODE",
                    supplemental.supplemental_assessment_id,
                    supplemental.reason_code,
                )
            if supplemental.uncertainty and supplemental.uncertainty.grade_set:
                self._add_fact(
                    facts,
                    "SUPPLEMENTAL_GRADE_SET",
                    supplemental.supplemental_assessment_id,
                    *supplemental.uncertainty.grade_set,
                )
            messages.append(
                _AllowedMessage(
                    "SUPPLEMENTAL_RESULT_AVAILABLE",
                    "추가 증빙을 반영한 결과가 확인됐습니다",
                    "품질검증을 통과한 증빙만 사용한 보완평가 상태를 설명합니다.",
                    (supplemental.supplemental_assessment_id,),
                )
                if supplemental.status == AssessmentStatus.COMPLETED
                else _AllowedMessage(
                    "SUPPLEMENTAL_RESULT_INCOMPLETE",
                    "보완평가가 완료되지 않았습니다",
                    "서버가 제공한 상태와 사유 코드를 확인하며 결과를 임의로 보완하지 않습니다.",
                    (supplemental.supplemental_assessment_id,),
                )
            )
            comparison = self.assessment_repository.get_latest_comparison(session_id)
            if (
                comparison is not None
                and comparison.supplemental_assessment_id != supplemental.supplemental_assessment_id
            ):
                comparison = None

        if comparison is not None:
            self._add_source(
                sources,
                ExplanationSourceType.ASSESSMENT_COMPARISON,
                comparison.comparison_id,
                data_version,
                comparison.supplemental_model_version,
                None,
            )
            self._add_fact(
                facts,
                "UNCERTAINTY_CHANGE",
                comparison.comparison_id,
                comparison.uncertainty_change.value,
            )
            self._add_fact(
                facts,
                "COMPARISON_RATIONALE_CODES",
                comparison.comparison_id,
                *comparison.rationale_codes,
            )
            comparison_copy = {
                AssessmentUncertaintyChange.NARROWED: (
                    "UNCERTAINTY_NARROWED",
                    "평가 결과 범위가 좁아졌습니다",
                    "검증된 증빙 반영 전보다 가능한 결과 범위가 줄어든 것으로 확인됐습니다.",
                ),
                AssessmentUncertaintyChange.UNCHANGED: (
                    "UNCERTAINTY_UNCHANGED",
                    "평가 결과 범위가 유지됐습니다",
                    "검증된 증빙을 반영했지만 가능한 결과 범위는 달라지지 않았습니다.",
                ),
                AssessmentUncertaintyChange.EXPANDED: (
                    "UNCERTAINTY_EXPANDED",
                    "평가 결과 범위가 넓어졌습니다",
                    "검증된 증빙 반영 후 가능한 결과 범위가 넓어져 자동 확정하지 않습니다.",
                ),
                AssessmentUncertaintyChange.SHIFTED: (
                    "UNCERTAINTY_SHIFTED",
                    "평가 결과 범위가 이동했습니다",
                    "검증된 증빙 반영 전후의 결과 범위가 서로 다른 구간으로 이동했습니다.",
                ),
                AssessmentUncertaintyChange.NOT_COMPARABLE: (
                    "UNCERTAINTY_NOT_COMPARABLE",
                    "평가 전후를 직접 비교할 수 없습니다",
                    "비교 기준이 일치하지 않아 변화의 방향을 임의로 해석하지 않습니다.",
                ),
            }[comparison.uncertainty_change]
            messages.append(_AllowedMessage(*comparison_copy, (comparison.comparison_id,)))
            resolution = self.boundary_repository.get_latest_resolution(session_id)
            if resolution is not None and resolution.comparison_id != comparison.comparison_id:
                resolution = None

        if resolution is not None:
            self._add_source(
                sources,
                ExplanationSourceType.EVIDENCE_RESOLUTION,
                resolution.resolution_id,
                data_version,
                None,
                resolution.boundary_policy_version,
            )
            self._add_fact(
                facts,
                "RESOLUTION_STATUS",
                resolution.resolution_id,
                resolution.status.value,
            )
            self._add_fact(
                facts,
                "RESOLUTION_NEXT_ACTION",
                resolution.resolution_id,
                resolution.next_action.value,
            )
            self._add_fact(
                facts,
                "RESOLUTION_REASON_CODE",
                resolution.resolution_id,
                resolution.reason_code,
            )
            if resolution.possible_routes:
                self._add_fact(
                    facts,
                    "RESOLUTION_POSSIBLE_ROUTES",
                    resolution.resolution_id,
                    *resolution.possible_routes,
                )
            if resolution.crossed_boundary_codes:
                self._add_fact(
                    facts,
                    "RESOLUTION_BOUNDARY_CODES",
                    resolution.resolution_id,
                    *resolution.crossed_boundary_codes,
                )
            resolution_copy = {
                EvidenceResolutionStatus.RESOLVED: (
                    "COLLECTION_RESOLVED",
                    "추가 증빙 수집이 종료됐습니다",
                    "하나의 정책 경로가 확인되어 현재 단계의 추가 증빙 수집을 중단했습니다.",
                ),
                EvidenceResolutionStatus.MORE_EVIDENCE_REQUIRED: (
                    "MORE_EVIDENCE_REQUIRED",
                    "추가 확인이 한 번 더 필요합니다",
                    "정책 경계의 불확실성이 남아 서버가 다음 최소 증빙 후보를 확인합니다.",
                ),
                EvidenceResolutionStatus.HUMAN_REVIEW: (
                    "UNDERWRITER_REVIEW_REQUIRED",
                    "심사역 검토로 전환됐습니다",
                    "자동으로 결과를 확정하지 않고 현재 근거와 함께 심사역 검토로 이관했습니다.",
                ),
            }[resolution.status]
            messages.append(_AllowedMessage(*resolution_copy, (resolution.resolution_id,)))

        snapshot = AssessmentExplanationInputSnapshot(
            session_id=session_id,
            target_type=target_type,
            target_assessment_id=target_assessment_id,
            facts=facts,
            source_references=sources,
        )
        return snapshot, messages

    def _validate_provider_plan(
        self,
        plan: ExplanationPlan,
        allowed_codes: tuple[str, ...],
    ) -> None:
        allowed = set(allowed_codes)
        if plan.headline_code not in allowed or not set(plan.section_codes).issubset(allowed):
            raise ValueError("provider selected a message code not allowed by current facts")
        selected_codes = set(plan.section_codes)
        server_ordered_codes = [code for code in allowed_codes if code in selected_codes]
        if plan.section_codes != server_ordered_codes:
            raise ValueError("provider cannot reorder server-owned explanation messages")
        required_current_state_code = allowed_codes[-1]
        if (
            plan.headline_code != required_current_state_code
            or required_current_state_code not in plan.section_codes
        ):
            raise ValueError("provider cannot omit or demote the latest required state")

    def _validate_provider_metadata(self) -> None:
        if not self.provider.provider_version.strip() or not self.provider.prompt_version.strip():
            raise ValueError("provider version metadata is required")
        if self.provider.rendering_mode == ExplanationRenderingMode.RULE_FALLBACK:
            raise ValueError("configured providers cannot claim RULE_FALLBACK mode")
        if self.provider.rendering_mode == ExplanationRenderingMode.GENERATIVE_AI:
            if not self.provider.model_version:
                raise ValueError("generative provider requires modelVersion")
        elif self.provider.model_version is not None:
            raise ValueError("template provider cannot expose modelVersion")

    @staticmethod
    def _fallback_plan(allowed_codes: tuple[str, ...]) -> ExplanationPlan:
        selected = list(allowed_codes[-8:])
        return ExplanationPlan(headline_code=selected[-1], section_codes=selected)

    @staticmethod
    def _snapshot_hash(snapshot: AssessmentExplanationInputSnapshot) -> str:
        serialized = json.dumps(
            snapshot.model_dump(mode="json", by_alias=True),
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode()).hexdigest()

    @staticmethod
    def _add_source(
        sources: list[ExplanationSourceReference],
        source_type: ExplanationSourceType,
        source_id: str,
        data_version: str | None,
        model_version: str | None,
        policy_version: str | None,
    ) -> None:
        sources.append(
            ExplanationSourceReference(
                source_type=source_type,
                source_id=source_id,
                data_version=data_version,
                model_version=model_version,
                policy_version=policy_version,
            )
        )

    @staticmethod
    def _add_fact(
        facts: list[ExplanationFact],
        fact_code: str,
        source_reference_id: str,
        *values: str,
    ) -> None:
        facts.append(
            ExplanationFact(
                fact_code=fact_code,
                source_reference_id=source_reference_id,
                values=list(values),
            )
        )
