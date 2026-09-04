from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.consent import ConsentSourceType
from app.schemas.data_source import (
    AdapterRetrievalResult,
    DemoDataSourceCatalogData,
    RetrievalStatus,
)


class DataSourceAdapter(ABC):
    @abstractmethod
    def retrieve(
        self,
        *,
        session_id: str,
        demo_profile_id: str,
        source_type: ConsentSourceType,
    ) -> AdapterRetrievalResult:
        """Retrieve verified metadata without exposing raw source data."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the adapter can process retrieval requests."""


class EmptyDemoDataSourceAdapter(DataSourceAdapter):
    """Explicitly reports missing Demo fixtures until Mock data is supplied."""

    def retrieve(
        self,
        *,
        session_id: str,
        demo_profile_id: str,
        source_type: ConsentSourceType,
    ) -> AdapterRetrievalResult:
        del session_id, demo_profile_id, source_type
        return AdapterRetrievalResult(
            retrieval_status=RetrievalStatus.NO_DATA,
            reason_code="DEMO_DATA_NOT_CONFIGURED",
        )

    def is_ready(self) -> bool:
        return True


class DemoDataSourceAdapter(DataSourceAdapter):
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoDataSourceCatalogData | None = None
        self._results: dict[tuple[str, ConsentSourceType], AdapterRetrievalResult] = {}

    def retrieve(
        self,
        *,
        session_id: str,
        demo_profile_id: str,
        source_type: ConsentSourceType,
    ) -> AdapterRetrievalResult:
        del session_id
        self._initialize()
        return self._results.get(
            (demo_profile_id, source_type),
            AdapterRetrievalResult(
                retrieval_status=RetrievalStatus.NO_DATA,
                reason_code="DEMO_DATA_NOT_CONFIGURED",
            ),
        )

    def is_ready(self) -> bool:
        try:
            self._initialize()
        except (OSError, ValueError):
            return False
        return True

    def _initialize(self) -> None:
        if self._catalog is not None:
            return
        catalog = DemoDataSourceCatalogData.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self._catalog = catalog
        self._results = {
            (item.demo_profile_id, item.source_type): item.result for item in catalog.sources
        }
