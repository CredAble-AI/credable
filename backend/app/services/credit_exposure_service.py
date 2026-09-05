from datetime import UTC, datetime
from pathlib import Path

from app.repositories.credit_exposure_repository import CreditExposureRepository
from app.schemas.credit_exposure import (
    CreditExposureSnapshot,
    DemoCreditExposureCatalog,
    DemoCreditExposureProfile,
)
from app.services.session_service import CustomerSessionService


class DemoCreditExposureCatalogService:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoCreditExposureCatalog | None = None
        self._profiles: dict[str, DemoCreditExposureProfile] = {}

    def initialize(self) -> None:
        catalog = DemoCreditExposureCatalog.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self._catalog = catalog
        self._profiles = {profile.demo_profile_id: profile for profile in catalog.profiles}

    @property
    def data_version(self) -> str:
        if self._catalog is None:
            raise RuntimeError("Demo credit exposure catalog is not initialized")
        return self._catalog.data_version

    def get(self, demo_profile_id: str) -> DemoCreditExposureProfile | None:
        return self._profiles.get(demo_profile_id)

    def is_ready(self) -> bool:
        return self._catalog is not None and bool(self._profiles)


class CreditExposureService:
    def __init__(
        self,
        repository: CreditExposureRepository,
        session_service: CustomerSessionService,
        catalog: DemoCreditExposureCatalogService,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()
        self.catalog.initialize()

    def get_or_materialize_snapshot(self, session_id: str) -> CreditExposureSnapshot:
        session = self.session_service.get_session(session_id).session
        stored = self.repository.get_snapshot(session_id)
        if stored is not None:
            return stored

        subject = session.customer_subject
        if subject is None:
            raise ValueError("customerSubject is required for credit exposures")
        profile = self.catalog.get(session.demo_profile.demo_profile_id)
        if profile is None:
            raise ValueError("Demo credit exposure is not configured for the session profile")
        if profile.borrower_id != subject.borrower.borrower_id:
            raise ValueError("credit exposure borrowerId does not match customerSubject")

        subject_business_id = (
            subject.primary_business.business_id if subject.primary_business is not None else None
        )
        if profile.primary_business_id != subject_business_id:
            raise ValueError("credit exposure primaryBusinessId does not match customerSubject")

        snapshot = CreditExposureSnapshot(
            session_id=session_id,
            borrower_id=profile.borrower_id,
            primary_business_id=profile.primary_business_id,
            provider_code=profile.provider_code,
            report_id=profile.report_id,
            reported_at=profile.reported_at,
            loaded_at=datetime.now(UTC),
            data_version=self.catalog.data_version,
            exposures=profile.exposures,
            delinquencies=profile.delinquencies,
            guarantees=profile.guarantees,
        )
        return self.repository.save_snapshot(snapshot)

    def materialize_if_version_matches(self, session_id: str, data_version: str | None) -> bool:
        if data_version != self.catalog.data_version:
            return False
        self.get_or_materialize_snapshot(session_id)
        return True

    def readiness(self) -> dict[str, bool]:
        return {
            "credit_exposure_repository": self.repository.is_ready(),
            "credit_exposure_catalog": self.catalog.is_ready(),
        }
