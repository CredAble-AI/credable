from fastapi import APIRouter, Request

from app.core.config import settings
from app.schemas.health import HealthResponse, ReadinessCheck, ReadinessResponse
from app.services.assessment_review_service import AssessmentReviewRequestService
from app.services.assessment_service import (
    AssessmentComparisonService,
    AssessmentService,
    SupplementalAssessmentService,
)
from app.services.bank_data_service import BankDataService
from app.services.consent_service import ConsentService
from app.services.credit_exposure_service import CreditExposureService
from app.services.credit_history_service import CreditHistoryService
from app.services.data_source_service import DataSourceService
from app.services.evidence_consent_service import EvidenceConsentService
from app.services.evidence_quality_service import EvidenceQualityService
from app.services.evidence_selection_service import EvidenceSelectionService
from app.services.evidence_submission_service import EvidenceSubmissionService
from app.services.feature_snapshot_service import FeatureSnapshotService
from app.services.loan_history_service import LoanHistoryService
from app.services.model_registry_service import ModelRegistryService
from app.services.policy_boundary_service import EvidenceResolutionService, PolicyBoundaryService
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService
from app.services.session_service import CustomerSessionService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Report whether the API process is running."""
    return HealthResponse(service=settings.slug)


@router.get("/ready", response_model=ReadinessResponse)
async def get_readiness(request: Request) -> ReadinessResponse:
    """Report whether the currently configured application dependencies are ready."""
    session_service: CustomerSessionService = request.app.state.session_service
    bank_data_service: BankDataService = request.app.state.bank_data_service
    credit_history_service: CreditHistoryService = request.app.state.credit_history_service
    loan_history_service: LoanHistoryService = request.app.state.loan_history_service
    credit_exposure_service: CreditExposureService = request.app.state.credit_exposure_service
    consent_service: ConsentService = request.app.state.consent_service
    data_source_service: DataSourceService = request.app.state.data_source_service
    assessment_service: AssessmentService = request.app.state.assessment_service
    assessment_review_request_service: AssessmentReviewRequestService = (
        request.app.state.assessment_review_request_service
    )
    feature_snapshot_service: FeatureSnapshotService = request.app.state.feature_snapshot_service
    model_registry_service: ModelRegistryService = request.app.state.model_registry_service
    supplemental_assessment_service: SupplementalAssessmentService = (
        request.app.state.supplemental_assessment_service
    )
    assessment_comparison_service: AssessmentComparisonService = (
        request.app.state.assessment_comparison_service
    )
    policy_boundary_service: PolicyBoundaryService = request.app.state.policy_boundary_service
    evidence_resolution_service: EvidenceResolutionService = (
        request.app.state.evidence_resolution_service
    )
    evidence_selection_service: EvidenceSelectionService = (
        request.app.state.evidence_selection_service
    )
    evidence_consent_service: EvidenceConsentService = request.app.state.evidence_consent_service
    evidence_submission_service: EvidenceSubmissionService = (
        request.app.state.evidence_submission_service
    )
    evidence_quality_service: EvidenceQualityService = request.app.state.evidence_quality_service
    product_catalog_service: ProductCatalogService = request.app.state.product_catalog_service
    product_condition_service: ProductConditionService = request.app.state.product_condition_service
    statuses = {
        "application": True,
        **session_service.readiness(),
        **bank_data_service.readiness(),
        **credit_history_service.readiness(),
        **loan_history_service.readiness(),
        **credit_exposure_service.readiness(),
        **consent_service.readiness(),
        **data_source_service.readiness(),
        **feature_snapshot_service.readiness(),
        **model_registry_service.readiness(),
        **assessment_service.readiness(),
        **assessment_review_request_service.readiness(),
        **supplemental_assessment_service.readiness(),
        **assessment_comparison_service.readiness(),
        **policy_boundary_service.readiness(),
        **evidence_resolution_service.readiness(),
        **evidence_selection_service.readiness(),
        **evidence_consent_service.readiness(),
        **evidence_submission_service.readiness(),
        **evidence_quality_service.readiness(),
        **product_catalog_service.readiness(),
        **product_condition_service.readiness(),
    }
    checks = [
        ReadinessCheck(name=name, status="ok" if ready else "error")
        for name, ready in statuses.items()
    ]
    overall_status = "ready" if all(statuses.values()) else "not_ready"
    return ReadinessResponse(status=overall_status, checks=checks)
