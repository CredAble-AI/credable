from datetime import UTC, datetime
from pathlib import Path

from app.repositories.credit_history_repository import CreditHistoryRepository
from app.schemas.credit_history import (
    CreditHistorySnapshot,
    DemoCreditHistoryCatalog,
    DemoCreditHistoryProfile,
)
from app.services.session_service import CustomerSessionService


class DemoCreditHistoryCatalogService:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoCreditHistoryCatalog | None = None
        self._profiles: dict[str, DemoCreditHistoryProfile] = {}

    def initialize(self) -> None:
        catalog = DemoCreditHistoryCatalog.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self._catalog = catalog
        self._profiles = {profile.demo_profile_id: profile for profile in catalog.profiles}

    @property
    def data_version(self) -> str:
        if self._catalog is None:
            raise RuntimeError("Demo credit history catalog is not initialized")
        return self._catalog.data_version

    def get(self, demo_profile_id: str) -> DemoCreditHistoryProfile | None:
        return self._profiles.get(demo_profile_id)

    def is_ready(self) -> bool:
        return self._catalog is not None and bool(self._profiles)


class CreditHistoryService:
    def __init__(
        self,
        repository: CreditHistoryRepository,
        session_service: CustomerSessionService,
        catalog: DemoCreditHistoryCatalogService,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()
        self.catalog.initialize()

    def get_or_materialize_snapshot(self, session_id: str) -> CreditHistorySnapshot:
        session = self.session_service.get_session(session_id).session
        stored = self.repository.get_snapshot(session_id)
        if stored is not None:
            return stored

        subject = session.customer_subject
        if subject is None:
            raise ValueError("customerSubject is required for credit history")
        profile = self.catalog.get(session.demo_profile.demo_profile_id)
        if profile is None:
            raise ValueError("Demo credit history is not configured for the session profile")
        if profile.borrower_id != subject.borrower.borrower_id:
            raise ValueError("credit history borrowerId does not match customerSubject")

        subject_business_id = (
            subject.primary_business.business_id if subject.primary_business is not None else None
        )
        if profile.primary_business_id != subject_business_id:
            raise ValueError("credit history primaryBusinessId does not match customerSubject")

        snapshot = CreditHistorySnapshot(
            session_id=session_id,
            borrower_id=profile.borrower_id,
            primary_business_id=profile.primary_business_id,
            observed_at=profile.observed_at,
            loaded_at=datetime.now(UTC),
            data_version=self.catalog.data_version,
            applications=profile.applications,
            decisions=profile.decisions,
            credit_assessments=profile.credit_assessments,
        )
        return self.repository.save_snapshot(snapshot)

    def materialize_if_version_matches(self, session_id: str, data_version: str | None) -> bool:
        if data_version != self.catalog.data_version:
            return False
        self.get_or_materialize_snapshot(session_id)
        return True

    def readiness(self) -> dict[str, bool]:
        return {
            "credit_history_repository": self.repository.is_ready(),
            "credit_history_catalog": self.catalog.is_ready(),
        }
