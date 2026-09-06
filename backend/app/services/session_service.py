import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import CustomerSessionNotFoundError, DemoProfileNotFoundError
from app.repositories.session_repository import CustomerSessionRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.customer import BusinessLegalForm
from app.schemas.session import (
    CustomerSession,
    CustomerSessionState,
    DemoProfileCatalogData,
    DemoProfileCatalogResponse,
    DemoProfileDefinition,
)


class DemoProfileCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoProfileCatalogData | None = None
        self._profiles_by_id: dict[str, DemoProfileDefinition] = {}
        self._profiles_by_borrower_type: dict[BusinessLegalForm, DemoProfileDefinition] = {}

    def initialize(self) -> None:
        catalog = DemoProfileCatalogData.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        profiles_by_id = {item.demo_profile_id: item for item in catalog.profiles}
        if len(profiles_by_id) != len(catalog.profiles):
            raise ValueError("demoProfileId values must be unique")
        # A borrower type now carries several demo cases (one per policy
        # boundary state), so the first one listed is its default.
        profiles_by_borrower_type: dict[BusinessLegalForm, DemoProfileDefinition] = {}
        for item in catalog.profiles:
            profiles_by_borrower_type.setdefault(item.business_borrower_type, item)
        self._catalog = catalog
        self._profiles_by_id = profiles_by_id
        self._profiles_by_borrower_type = profiles_by_borrower_type

    @property
    def data_version(self) -> str:
        if self._catalog is None:
            raise RuntimeError("Demo Profile catalog is not initialized")
        return self._catalog.data_version

    @property
    def profile_ids(self) -> tuple[str, ...]:
        return tuple(self._profiles_by_id)

    @property
    def profiles(self) -> tuple[DemoProfileDefinition, ...]:
        return tuple(self._profiles_by_id.values())

    @property
    def business_borrower_types(self) -> tuple[BusinessLegalForm, ...]:
        return tuple(self._profiles_by_borrower_type)

    def get(self, demo_profile_id: str) -> DemoProfileDefinition | None:
        return self._profiles_by_id.get(demo_profile_id)

    def get_by_business_borrower_type(
        self,
        business_borrower_type: BusinessLegalForm,
    ) -> DemoProfileDefinition | None:
        return self._profiles_by_borrower_type.get(business_borrower_type)

    def is_ready(self) -> bool:
        return (
            self._catalog is not None
            and bool(self._profiles_by_id)
            and bool(self._profiles_by_borrower_type)
        )


class CustomerSessionService:
    def __init__(
        self,
        repository: CustomerSessionRepository,
        catalog: DemoProfileCatalog,
    ) -> None:
        self.repository = repository
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()
        self.catalog.initialize()

    def create_demo_session(
        self,
        demo_profile_id: str | None,
        business_borrower_type: BusinessLegalForm | None,
        request_id: str,
    ) -> CustomerSessionState:
        definition = None
        if demo_profile_id is not None:
            definition = self.catalog.get(demo_profile_id)
        elif business_borrower_type is not None:
            definition = self.catalog.get_by_business_borrower_type(business_borrower_type)
        if definition is None:
            selector = demo_profile_id or (
                business_borrower_type.value if business_borrower_type is not None else "missing"
            )
            raise DemoProfileNotFoundError(selector)

        created_at = datetime.now(UTC)
        session = CustomerSession(
            session_id=f"ses_{uuid4().hex}",
            demo_profile=definition.to_profile(),
            customer_subject=definition.customer_subject,
            created_at=created_at,
            data_version=self.catalog.data_version,
        )
        state = CustomerSessionState(session=session)
        profile_snapshot = definition.model_dump(mode="json", by_alias=True)
        snapshot_json = json.dumps(
            profile_snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        output_summary: dict[str, str | bool | int | float] = {
            "demoProfileId": definition.demo_profile_id,
            "businessBorrowerType": definition.business_borrower_type.value,
            "borrowerId": definition.customer_subject.borrower.borrower_id,
            "demoOnly": session.demo_only,
        }
        if definition.customer_subject.primary_business is not None:
            output_summary["primaryBusinessId"] = (
                definition.customer_subject.primary_business.business_id
            )

        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session.session_id,
            request_id=request_id,
            stage=AuditStage.SESSION_CREATED,
            timestamp=created_at,
            actor=AuditActor.SYSTEM,
            input_version=self.catalog.data_version,
            input_snapshot_hash=hashlib.sha256(snapshot_json.encode()).hexdigest(),
            output_summary=output_summary,
            data_version=self.catalog.data_version,
        )
        return self.repository.create_session(state=state, audit_event=audit_event)

    def get_session(self, session_id: str) -> CustomerSessionState:
        state = self.repository.get_session(session_id)
        if state is None:
            raise CustomerSessionNotFoundError(session_id)
        return state

    def list_demo_profiles(self) -> DemoProfileCatalogResponse:
        return DemoProfileCatalogResponse(
            data_version=self.catalog.data_version,
            profiles=[definition.to_profile() for definition in self.catalog.profiles],
        )

    def readiness(self) -> dict[str, bool]:
        return {
            "session_repository": self.repository.is_ready(),
            "demo_profiles": self.catalog.is_ready(),
        }
