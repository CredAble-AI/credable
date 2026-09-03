from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.repositories.case_repository import SqliteCaseRepository
from app.services.case_service import CaseService, DemoCaseCatalog


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
def client(case_service: CaseService) -> Generator[TestClient]:
    with TestClient(create_app(case_service=case_service)) as test_client:
        yield test_client
