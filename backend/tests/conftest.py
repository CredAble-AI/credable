from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import UnconfiguredDemoAssessmentAdapter
from app.adapters.data_source_adapter import EmptyDemoDataSourceAdapter
from app.adapters.product_catalog_adapter import UnconfiguredProductCatalogAdapter
from app.adapters.product_condition_adapter import UnconfiguredProductConditionAdapter
from app.core.config import settings
from app.main import create_app
from app.repositories.assessment_repository import SqliteAssessmentRepository
from app.repositories.case_repository import SqliteCaseRepository
from app.repositories.consent_repository import SqliteConsentRepository
from app.repositories.data_source_repository import SqliteDataSourceRepository
from app.repositories.product_catalog_repository import SqliteProductCatalogRepository
from app.repositories.product_condition_repository import SqliteProductConditionRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.services.assessment_service import AssessmentService
from app.services.case_service import CaseService, DemoCaseCatalog
from app.services.consent_service import ConsentService, DemoConsentScopeCatalog
from app.services.data_source_service import DataSourceService
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService
from app.services.session_service import CustomerSessionService, DemoProfileCatalog


@pytest.fixture
def case_repository(tmp_path) -> SqliteCaseRepository:
    return SqliteCaseRepository(tmp_path / "test.db")


@pytest.fixture
def case_service(case_repository: SqliteCaseRepository) -> CaseService:
    return CaseService(
        repository=case_repository,
        catalog=DemoCaseCatalog(settings.demo_cases_path),
    )


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
    case_service: CaseService,
    session_service: CustomerSessionService,
    consent_service: ConsentService,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> Generator[TestClient]:
    with TestClient(
        create_app(
            case_service=case_service,
            session_service=session_service,
            consent_service=consent_service,
            data_source_service=data_source_service,
            assessment_service=assessment_service,
            product_catalog_service=product_catalog_service,
            product_condition_service=product_condition_service,
        )
    ) as test_client:
        yield test_client
