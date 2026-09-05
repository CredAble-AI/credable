from fastapi import APIRouter, Request

from app.core.config import settings
from app.schemas.health import HealthResponse, ReadinessCheck, ReadinessResponse
from app.services.assessment_service import (
    AssessmentComparisonService,
    AssessmentService,
    SupplementalAssessmentService,
)
from app.services.bank_data_service import BankDataService
from app.services.consent_service import ConsentService
from app.services.data_source_service import DataSourceService
from app.services.evidence_quality_service import EvidenceQualityService
from app.services.evidence_selection_service import EvidenceSelectionService
from app.services.evidence_submission_service import EvidenceSubmissionService
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
    consent_service: ConsentService = request.app.state.consent_service
    data_source_service: DataSourceService = request.app.state.data_source_service
    assessment_service: AssessmentService = request.app.state.assessment_service
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
        **consent_service.readiness(),
        **data_source_service.readiness(),
        **assessment_service.readiness(),
        **supplemental_assessment_service.readiness(),
        **assessment_comparison_service.readiness(),
        **policy_boundary_service.readiness(),
        **evidence_resolution_service.readiness(),
        **evidence_selection_service.readiness(),
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
