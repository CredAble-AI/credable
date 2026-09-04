from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.repositories.case_repository import SqliteCaseRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.services.case_service import CaseService, DemoCaseCatalog
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
def client(
    case_service: CaseService,
    session_service: CustomerSessionService,
) -> Generator[TestClient]:
    with TestClient(
        create_app(case_service=case_service, session_service=session_service)
    ) as test_client:
        yield test_client
