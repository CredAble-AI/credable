from datetime import UTC, datetime
from pathlib import Path

from app.repositories.loan_history_repository import LoanHistoryRepository
from app.schemas.loan_history import (
    DemoLoanHistoryCatalog,
    DemoLoanHistoryProfile,
    LoanHistorySnapshot,
)
from app.services.session_service import CustomerSessionService


class DemoLoanHistoryCatalogService:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoLoanHistoryCatalog | None = None
        self._profiles: dict[str, DemoLoanHistoryProfile] = {}

    def initialize(self) -> None:
        catalog = DemoLoanHistoryCatalog.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self._catalog = catalog
        self._profiles = {profile.demo_profile_id: profile for profile in catalog.profiles}

    @property
    def data_version(self) -> str:
        if self._catalog is None:
            raise RuntimeError("Demo loan history catalog is not initialized")
        return self._catalog.data_version

    def get(self, demo_profile_id: str) -> DemoLoanHistoryProfile | None:
        return self._profiles.get(demo_profile_id)

    def is_ready(self) -> bool:
        return self._catalog is not None and bool(self._profiles)


class LoanHistoryService:
    def __init__(
        self,
        repository: LoanHistoryRepository,
        session_service: CustomerSessionService,
        catalog: DemoLoanHistoryCatalogService,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()
        self.catalog.initialize()

    def get_or_materialize_snapshot(self, session_id: str) -> LoanHistorySnapshot:
        session = self.session_service.get_session(session_id).session
        stored = self.repository.get_snapshot(session_id)
        if stored is not None:
            return stored

        subject = session.customer_subject
        if subject is None:
            raise ValueError("customerSubject is required for loan history")
        profile = self.catalog.get(session.demo_profile.demo_profile_id)
        if profile is None:
            raise ValueError("Demo loan history is not configured for the session profile")
        if profile.borrower_id != subject.borrower.borrower_id:
            raise ValueError("loan history borrowerId does not match customerSubject")

        subject_business_id = (
            subject.primary_business.business_id if subject.primary_business is not None else None
        )
        if profile.primary_business_id != subject_business_id:
            raise ValueError("loan history primaryBusinessId does not match customerSubject")

        snapshot = LoanHistorySnapshot(
            session_id=session_id,
            borrower_id=profile.borrower_id,
            primary_business_id=profile.primary_business_id,
            observed_at=profile.observed_at,
            loaded_at=datetime.now(UTC),
            data_version=self.catalog.data_version,
            loan_accounts=profile.loan_accounts,
            repayment_schedules=profile.repayment_schedules,
            repayment_events=profile.repayment_events,
            delinquency_events=profile.delinquency_events,
        )
        return self.repository.save_snapshot(snapshot)

    def materialize_if_version_matches(self, session_id: str, data_version: str | None) -> bool:
        if data_version != self.catalog.data_version:
            return False
        self.get_or_materialize_snapshot(session_id)
        return True

    def readiness(self) -> dict[str, bool]:
        return {
            "loan_history_repository": self.repository.is_ready(),
            "loan_history_catalog": self.catalog.is_ready(),
        }
