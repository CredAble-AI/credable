from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    UnconfiguredDemoAssessmentAdapter,
    UnconfiguredSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import EmptyDemoDataSourceAdapter
from app.adapters.product_catalog_adapter import UnconfiguredProductCatalogAdapter
from app.adapters.product_condition_adapter import UnconfiguredProductConditionAdapter
from app.core.admin_auth import AdminApiKeyAuthenticator
from app.core.config import settings
from app.main import create_app
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
from app.services.assessment_service import (
    AssessmentComparisonService,
    AssessmentService,
    SupplementalAssessmentService,
)
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
from app.services.policy_boundary_service import (
    DemoPolicyBoundaryCatalog,
    EvidenceResolutionService,
    PolicyBoundaryService,
)
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService
from app.services.session_service import CustomerSessionService, DemoProfileCatalog


@pytest.fixture
def session_repository(tmp_path) -> SqliteCustomerSessionRepository:
    return SqliteCustomerSessionRepository(tmp_path / "test.db")


@pytest.fixture
def session_service(
    session_repository: SqliteCustomerSessionRepository,
) -> CustomerSessionService:
    return CustomerSessionService(
        repository=session_repository,
        catalog=DemoProfileCatalog(settings.demo_profiles_path),
    )


@pytest.fixture
def consent_repository(tmp_path) -> SqliteConsentRepository:
    return SqliteConsentRepository(tmp_path / "test.db")


@pytest.fixture
def consent_service(
    consent_repository: SqliteConsentRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> ConsentService:
    return ConsentService(
        repository=consent_repository,
        session_repository=session_repository,
        catalog=DemoConsentScopeCatalog(settings.demo_consent_scopes_path),
    )


@pytest.fixture
def data_source_repository(tmp_path) -> SqliteDataSourceRepository:
    return SqliteDataSourceRepository(tmp_path / "test.db")


@pytest.fixture
def data_source_service(
    data_source_repository: SqliteDataSourceRepository,
    consent_service: ConsentService,
    session_service: CustomerSessionService,
) -> DataSourceService:
    return DataSourceService(
        repository=data_source_repository,
        consent_service=consent_service,
        session_service=session_service,
        adapter=EmptyDemoDataSourceAdapter(),
    )


@pytest.fixture
def assessment_repository(tmp_path) -> SqliteAssessmentRepository:
    return SqliteAssessmentRepository(tmp_path / "test.db")


@pytest.fixture
def assessment_service(
    assessment_repository: SqliteAssessmentRepository,
    session_service: CustomerSessionService,
    data_source_service: DataSourceService,
) -> AssessmentService:
    return AssessmentService(
        repository=assessment_repository,
        session_service=session_service,
        data_source_service=data_source_service,
        adapter=UnconfiguredDemoAssessmentAdapter(),
    )


@pytest.fixture
def policy_boundary_repository(tmp_path) -> SqlitePolicyBoundaryRepository:
    return SqlitePolicyBoundaryRepository(tmp_path / "test.db")


@pytest.fixture
def policy_boundary_service(
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    session_service: CustomerSessionService,
    assessment_service: AssessmentService,
) -> PolicyBoundaryService:
    return PolicyBoundaryService(
        repository=policy_boundary_repository,
        session_service=session_service,
        assessment_service=assessment_service,
        catalog=DemoPolicyBoundaryCatalog(settings.demo_policy_boundaries_path),
    )


@pytest.fixture
def evidence_selection_repository(tmp_path) -> SqliteEvidenceSelectionRepository:
    return SqliteEvidenceSelectionRepository(tmp_path / "test.db")


@pytest.fixture
def evidence_selection_service(
    evidence_selection_repository: SqliteEvidenceSelectionRepository,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    assessment_repository: SqliteAssessmentRepository,
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    session_service: CustomerSessionService,
    policy_boundary_service: PolicyBoundaryService,
    data_source_service: DataSourceService,
) -> EvidenceSelectionService:
    return EvidenceSelectionService(
        repository=evidence_selection_repository,
        session_service=session_service,
        boundary_service=policy_boundary_service,
        data_source_service=data_source_service,
        assessment_repository=assessment_repository,
        resolution_repository=policy_boundary_repository,
        submission_repository=evidence_submission_repository,
        catalog=DemoEvidenceCandidateCatalog(settings.demo_evidence_candidates_path),
    )


@pytest.fixture
def evidence_submission_repository(tmp_path) -> SqliteEvidenceSubmissionRepository:
    return SqliteEvidenceSubmissionRepository(tmp_path / "test.db")


@pytest.fixture
def evidence_submission_service(
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    session_service: CustomerSessionService,
    evidence_selection_service: EvidenceSelectionService,
) -> EvidenceSubmissionService:
    return EvidenceSubmissionService(
        repository=evidence_submission_repository,
        session_service=session_service,
        selection_service=evidence_selection_service,
        catalog=DemoEvidenceSubmissionCatalog(settings.demo_evidence_submissions_path),
    )


@pytest.fixture
def evidence_quality_repository(tmp_path) -> SqliteEvidenceQualityRepository:
    return SqliteEvidenceQualityRepository(tmp_path / "test.db")


@pytest.fixture
def evidence_quality_service(
    evidence_quality_repository: SqliteEvidenceQualityRepository,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    session_service: CustomerSessionService,
) -> EvidenceQualityService:
    return EvidenceQualityService(
        repository=evidence_quality_repository,
        submission_repository=evidence_submission_repository,
        session_service=session_service,
        catalog=DemoEvidenceQualityCatalog(settings.demo_evidence_quality_path),
    )


@pytest.fixture
def supplemental_assessment_service(
    assessment_repository: SqliteAssessmentRepository,
    session_service: CustomerSessionService,
    evidence_quality_repository: SqliteEvidenceQualityRepository,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    evidence_selection_repository: SqliteEvidenceSelectionRepository,
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
) -> SupplementalAssessmentService:
    return SupplementalAssessmentService(
        repository=assessment_repository,
        session_service=session_service,
        quality_repository=evidence_quality_repository,
        submission_repository=evidence_submission_repository,
        selection_repository=evidence_selection_repository,
        boundary_repository=policy_boundary_repository,
        adapter=UnconfiguredSupplementalAssessmentAdapter(),
    )


@pytest.fixture
def assessment_comparison_service(
    assessment_repository: SqliteAssessmentRepository,
    session_service: CustomerSessionService,
) -> AssessmentComparisonService:
    return AssessmentComparisonService(
        repository=assessment_repository,
        session_service=session_service,
    )


@pytest.fixture
def evidence_resolution_service(
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    assessment_repository: SqliteAssessmentRepository,
    session_service: CustomerSessionService,
    policy_boundary_service: PolicyBoundaryService,
) -> EvidenceResolutionService:
    return EvidenceResolutionService(
        repository=policy_boundary_repository,
        assessment_repository=assessment_repository,
        session_service=session_service,
        catalog=policy_boundary_service.catalog,
    )


@pytest.fixture
def product_catalog_repository(tmp_path) -> SqliteProductCatalogRepository:
    return SqliteProductCatalogRepository(tmp_path / "test.db")


@pytest.fixture
def product_catalog_service(
    product_catalog_repository: SqliteProductCatalogRepository,
    session_service: CustomerSessionService,
) -> ProductCatalogService:
    return ProductCatalogService(
        repository=product_catalog_repository,
        session_service=session_service,
        adapter=UnconfiguredProductCatalogAdapter(),
    )


@pytest.fixture
def product_condition_repository(tmp_path) -> SqliteProductConditionRepository:
    return SqliteProductConditionRepository(tmp_path / "test.db")


@pytest.fixture
def product_condition_service(
    product_condition_repository: SqliteProductConditionRepository,
    session_service: CustomerSessionService,
    product_catalog_service: ProductCatalogService,
    assessment_service: AssessmentService,
    data_source_service: DataSourceService,
) -> ProductConditionService:
    return ProductConditionService(
        repository=product_condition_repository,
        session_service=session_service,
        catalog_service=product_catalog_service,
        assessment_service=assessment_service,
        data_source_service=data_source_service,
        adapter=UnconfiguredProductConditionAdapter(),
    )


@pytest.fixture
def client(
    session_service: CustomerSessionService,
    consent_service: ConsentService,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    policy_boundary_service: PolicyBoundaryService,
    evidence_selection_service: EvidenceSelectionService,
    evidence_submission_service: EvidenceSubmissionService,
    evidence_quality_service: EvidenceQualityService,
    supplemental_assessment_service: SupplementalAssessmentService,
    assessment_comparison_service: AssessmentComparisonService,
    evidence_resolution_service: EvidenceResolutionService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> Generator[TestClient]:
    with TestClient(
        create_app(
            session_service=session_service,
            consent_service=consent_service,
            data_source_service=data_source_service,
            assessment_service=assessment_service,
            policy_boundary_service=policy_boundary_service,
            evidence_selection_service=evidence_selection_service,
            evidence_submission_service=evidence_submission_service,
            evidence_quality_service=evidence_quality_service,
            supplemental_assessment_service=supplemental_assessment_service,
            assessment_comparison_service=assessment_comparison_service,
            evidence_resolution_service=evidence_resolution_service,
            product_catalog_service=product_catalog_service,
            product_condition_service=product_condition_service,
            admin_authenticator=AdminApiKeyAuthenticator("test-admin-api-key"),
        )
    ) as test_client:
        yield test_client
