from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.responses import JSONResponse

from app.adapters.assessment_adapter import (
    DemoAssessmentAdapter,
    DemoSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.adapters.product_catalog_adapter import DemoProductCatalogAdapter
from app.adapters.product_condition_adapter import DemoProductConditionAdapter
from app.api.admin_audit import router as admin_audit_router
from app.api.demo_profiles import router as demo_profiles_router
from app.api.health import router as health_router
from app.api.sessions import router as sessions_router
from app.core.admin_auth import AdminApiKeyAuthenticator
from app.core.config import settings
from app.core.errors import ApiDomainError
from app.repositories.assessment_repository import SqliteAssessmentRepository
from app.repositories.consent_repository import SqliteConsentRepository
from app.repositories.data_source_repository import SqliteDataSourceRepository
from app.repositories.evidence_quality_repository import SqliteEvidenceQualityRepository
from app.repositories.evidence_selection_repository import SqliteEvidenceSelectionRepository
from app.repositories.evidence_submission_repository import SqliteEvidenceSubmissionRepository
from app.repositories.policy_boundary_repository import SqlitePolicyBoundaryRepository
from app.repositories.product_catalog_repository import SqliteProductCatalogRepository
from app.repositories.product_condition_repository import SqliteProductConditionRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.error import ApiErrorDetail, ApiErrorResponse
from app.services.admin_audit_service import AdminAuditService
from app.services.assessment_service import (
    AssessmentComparisonService,
    AssessmentService,
    SupplementalAssessmentService,
)
from app.services.comparison_service import ProductComparisonService
from app.services.consent_service import ConsentService, DemoConsentScopeCatalog
from app.services.data_source_service import DataSourceService
from app.services.evidence_quality_service import (
    DemoEvidenceQualityCatalog,
    EvidenceQualityService,
)
from app.services.evidence_selection_service import (
    DemoEvidenceCandidateCatalog,
    EvidenceSelectionService,
)
from app.services.evidence_submission_service import (
    DemoEvidenceSubmissionCatalog,
    EvidenceSubmissionService,
)
from app.services.policy_boundary_service import DemoPolicyBoundaryCatalog, PolicyBoundaryService
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService
from app.services.session_service import CustomerSessionService, DemoProfileCatalog


def build_session_service() -> CustomerSessionService:
    return CustomerSessionService(
        repository=SqliteCustomerSessionRepository(settings.database_path),
        catalog=DemoProfileCatalog(settings.demo_profiles_path),
    )


def build_admin_authenticator() -> AdminApiKeyAuthenticator:
    api_key = settings.admin_api_key.get_secret_value() if settings.admin_api_key else None
    return AdminApiKeyAuthenticator(api_key)


def build_consent_service(session_service: CustomerSessionService) -> ConsentService:
    return ConsentService(
        repository=SqliteConsentRepository(settings.database_path),
        session_repository=session_service.repository,
        catalog=DemoConsentScopeCatalog(settings.demo_consent_scopes_path),
    )


def build_data_source_service(
    consent_service: ConsentService,
    session_service: CustomerSessionService,
) -> DataSourceService:
    return DataSourceService(
        repository=SqliteDataSourceRepository(settings.database_path),
        consent_service=consent_service,
        session_service=session_service,
        adapter=DemoDataSourceAdapter(settings.demo_data_sources_path),
    )


def build_assessment_service(
    session_service: CustomerSessionService,
    data_source_service: DataSourceService,
) -> AssessmentService:
    return AssessmentService(
        repository=SqliteAssessmentRepository(settings.database_path),
        session_service=session_service,
        data_source_service=data_source_service,
        adapter=DemoAssessmentAdapter(settings.demo_assessments_path),
    )


def build_product_catalog_service(
    session_service: CustomerSessionService,
) -> ProductCatalogService:
    return ProductCatalogService(
        repository=SqliteProductCatalogRepository(settings.database_path),
        session_service=session_service,
        adapter=DemoProductCatalogAdapter(settings.demo_products_path),
    )


def build_policy_boundary_service(
    session_service: CustomerSessionService,
    assessment_service: AssessmentService,
) -> PolicyBoundaryService:
    return PolicyBoundaryService(
        repository=SqlitePolicyBoundaryRepository(settings.database_path),
        session_service=session_service,
        assessment_service=assessment_service,
        catalog=DemoPolicyBoundaryCatalog(settings.demo_policy_boundaries_path),
    )


def build_evidence_selection_service(
    session_service: CustomerSessionService,
    policy_boundary_service: PolicyBoundaryService,
    data_source_service: DataSourceService,
) -> EvidenceSelectionService:
    return EvidenceSelectionService(
        repository=SqliteEvidenceSelectionRepository(settings.database_path),
        session_service=session_service,
        boundary_service=policy_boundary_service,
        data_source_service=data_source_service,
        catalog=DemoEvidenceCandidateCatalog(settings.demo_evidence_candidates_path),
    )


def build_evidence_submission_service(
    session_service: CustomerSessionService,
    evidence_selection_service: EvidenceSelectionService,
) -> EvidenceSubmissionService:
    return EvidenceSubmissionService(
        repository=SqliteEvidenceSubmissionRepository(settings.database_path),
        session_service=session_service,
        selection_service=evidence_selection_service,
        catalog=DemoEvidenceSubmissionCatalog(settings.demo_evidence_submissions_path),
    )


def build_evidence_quality_service(
    session_service: CustomerSessionService,
    evidence_submission_service: EvidenceSubmissionService,
) -> EvidenceQualityService:
    return EvidenceQualityService(
        repository=SqliteEvidenceQualityRepository(settings.database_path),
        submission_repository=evidence_submission_service.repository,
        session_service=session_service,
        catalog=DemoEvidenceQualityCatalog(settings.demo_evidence_quality_path),
    )


def build_supplemental_assessment_service(
    session_service: CustomerSessionService,
    assessment_service: AssessmentService,
    policy_boundary_service: PolicyBoundaryService,
    evidence_selection_service: EvidenceSelectionService,
    evidence_submission_service: EvidenceSubmissionService,
    evidence_quality_service: EvidenceQualityService,
) -> SupplementalAssessmentService:
    return SupplementalAssessmentService(
        repository=assessment_service.repository,
        session_service=session_service,
        quality_repository=evidence_quality_service.repository,
        submission_repository=evidence_submission_service.repository,
        selection_repository=evidence_selection_service.repository,
        boundary_repository=policy_boundary_service.repository,
        adapter=DemoSupplementalAssessmentAdapter(settings.demo_supplemental_assessments_path),
    )


def build_assessment_comparison_service(
    session_service: CustomerSessionService,
    assessment_service: AssessmentService,
) -> AssessmentComparisonService:
    return AssessmentComparisonService(
        repository=assessment_service.repository,
        session_service=session_service,
    )


def build_product_condition_service(
    session_service: CustomerSessionService,
    product_catalog_service: ProductCatalogService,
    assessment_service: AssessmentService,
    data_source_service: DataSourceService,
) -> ProductConditionService:
    return ProductConditionService(
        repository=SqliteProductConditionRepository(settings.database_path),
        session_service=session_service,
        catalog_service=product_catalog_service,
        assessment_service=assessment_service,
        data_source_service=data_source_service,
        adapter=DemoProductConditionAdapter(settings.demo_product_conditions_path),
    )


def create_app(
    session_service: CustomerSessionService | None = None,
    consent_service: ConsentService | None = None,
    data_source_service: DataSourceService | None = None,
    assessment_service: AssessmentService | None = None,
    policy_boundary_service: PolicyBoundaryService | None = None,
    evidence_selection_service: EvidenceSelectionService | None = None,
    evidence_submission_service: EvidenceSubmissionService | None = None,
    evidence_quality_service: EvidenceQualityService | None = None,
    supplemental_assessment_service: SupplementalAssessmentService | None = None,
    assessment_comparison_service: AssessmentComparisonService | None = None,
    product_catalog_service: ProductCatalogService | None = None,
    product_condition_service: ProductConditionService | None = None,
    admin_authenticator: AdminApiKeyAuthenticator | None = None,
) -> FastAPI:
    resolved_session_service = session_service or build_session_service()
    resolved_consent_service = consent_service or build_consent_service(resolved_session_service)
    resolved_data_source_service = data_source_service or build_data_source_service(
        resolved_consent_service,
        resolved_session_service,
    )
    resolved_assessment_service = assessment_service or build_assessment_service(
        resolved_session_service,
        resolved_data_source_service,
    )
    resolved_policy_boundary_service = policy_boundary_service or build_policy_boundary_service(
        resolved_session_service,
        resolved_assessment_service,
    )
    resolved_evidence_selection_service = (
        evidence_selection_service
        or build_evidence_selection_service(
            resolved_session_service,
            resolved_policy_boundary_service,
            resolved_data_source_service,
        )
    )
    resolved_evidence_submission_service = (
        evidence_submission_service
        or build_evidence_submission_service(
            resolved_session_service,
            resolved_evidence_selection_service,
        )
    )
    resolved_evidence_quality_service = evidence_quality_service or build_evidence_quality_service(
        resolved_session_service,
        resolved_evidence_submission_service,
    )
    resolved_supplemental_assessment_service = (
        supplemental_assessment_service
        or build_supplemental_assessment_service(
            resolved_session_service,
            resolved_assessment_service,
            resolved_policy_boundary_service,
            resolved_evidence_selection_service,
            resolved_evidence_submission_service,
            resolved_evidence_quality_service,
        )
    )
    resolved_assessment_comparison_service = (
        assessment_comparison_service
        or build_assessment_comparison_service(
            resolved_session_service,
            resolved_assessment_service,
        )
    )
    resolved_product_catalog_service = product_catalog_service or build_product_catalog_service(
        resolved_session_service
    )
    resolved_product_condition_service = (
        product_condition_service
        or build_product_condition_service(
            resolved_session_service,
            resolved_product_catalog_service,
            resolved_assessment_service,
            resolved_data_source_service,
        )
    )
    resolved_product_comparison_service = ProductComparisonService(
        session_service=resolved_session_service,
        catalog_service=resolved_product_catalog_service,
        condition_service=resolved_product_condition_service,
    )
    resolved_admin_authenticator = admin_authenticator or build_admin_authenticator()
    resolved_admin_audit_service = AdminAuditService(resolved_session_service)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_session_service.initialize()
        resolved_consent_service.initialize()
        resolved_data_source_service.initialize()
        resolved_assessment_service.initialize()
        resolved_policy_boundary_service.initialize()
        resolved_evidence_selection_service.initialize()
        resolved_evidence_submission_service.initialize()
        resolved_evidence_quality_service.initialize()
        resolved_supplemental_assessment_service.initialize()
        resolved_assessment_comparison_service.initialize()
        resolved_product_catalog_service.initialize()
        resolved_product_condition_service.initialize()
        yield

    application = FastAPI(
        title=settings.name,
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.session_service = resolved_session_service
    application.state.consent_service = resolved_consent_service
    application.state.data_source_service = resolved_data_source_service
    application.state.assessment_service = resolved_assessment_service
    application.state.policy_boundary_service = resolved_policy_boundary_service
    application.state.evidence_selection_service = resolved_evidence_selection_service
    application.state.evidence_submission_service = resolved_evidence_submission_service
    application.state.evidence_quality_service = resolved_evidence_quality_service
    application.state.supplemental_assessment_service = resolved_supplemental_assessment_service
    application.state.assessment_comparison_service = resolved_assessment_comparison_service
    application.state.product_catalog_service = resolved_product_catalog_service
    application.state.product_condition_service = resolved_product_condition_service
    application.state.product_comparison_service = resolved_product_comparison_service
    application.state.admin_authenticator = resolved_admin_authenticator
    application.state.admin_audit_service = resolved_admin_audit_service

    @application.middleware("http")
    async def attach_request_id(request: FastAPIRequest, call_next):
        request.state.request_id = f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(ApiDomainError)
    async def handle_domain_error(
        request: FastAPIRequest,
        error: ApiDomainError,
    ) -> JSONResponse:
        response = ApiErrorResponse(
            error=ApiErrorDetail(
                code=error.code,
                message=error.message,
                request_id=request.state.request_id,
                retryable=error.retryable,
            )
        )
        return JSONResponse(
            status_code=error.status_code,
            content=response.model_dump(mode="json", by_alias=True),
        )

    application.include_router(health_router)
    application.include_router(demo_profiles_router)
    application.include_router(sessions_router)
    application.include_router(admin_audit_router)
    return application


app = create_app()
