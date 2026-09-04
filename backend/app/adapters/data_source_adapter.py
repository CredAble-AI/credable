from abc import ABC, abstractmethod

from app.schemas.consent import ConsentSourceType
from app.schemas.data_source import AdapterRetrievalResult, RetrievalStatus


class DataSourceAdapter(ABC):
    @abstractmethod
    def retrieve(
        self,
        *,
        session_id: str,
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
        source_type: ConsentSourceType,
    ) -> AdapterRetrievalResult:
        del session_id, source_type
        return AdapterRetrievalResult(
            retrieval_status=RetrievalStatus.NO_DATA,
            reason_code="DEMO_DATA_NOT_CONFIGURED",
        )

    def is_ready(self) -> bool:
        return True
