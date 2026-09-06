import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import (
    ConsentNotGrantedError,
    ConsentScopeNotFoundError,
    CustomerSessionNotFoundError,
)
from app.repositories.consent_repository import ConsentRepository
from app.repositories.session_repository import CustomerSessionRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.consent import (
    ConsentListResponse,
    ConsentScopeCatalogData,
    ConsentScopeDefinition,
    ConsentSourceType,
    ConsentState,
    ConsentStatus,
)


class DemoConsentScopeCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: ConsentScopeCatalogData | None = None
        self._scopes_by_type: dict[ConsentSourceType, ConsentScopeDefinition] = {}

    def initialize(self) -> None:
        catalog = ConsentScopeCatalogData.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        scopes_by_type = {item.source_type: item for item in catalog.scopes}
        if len(scopes_by_type) != len(catalog.scopes):
            raise ValueError("sourceType values must be unique")
        self._catalog = catalog
        self._scopes_by_type = scopes_by_type

    @property
    def data_version(self) -> str:
        if self._catalog is None:
            raise RuntimeError("Demo Consent Scope catalog is not initialized")
        return self._catalog.data_version

    @property
    def scopes(self) -> tuple[ConsentScopeDefinition, ...]:
        return tuple(self._scopes_by_type.values())

    def get(self, source_type: str) -> ConsentScopeDefinition | None:
        try:
            parsed = ConsentSourceType(source_type)
        except ValueError:
            return None
        return self._scopes_by_type.get(parsed)

    def is_ready(self) -> bool:
        return self._catalog is not None and bool(self._scopes_by_type)


class ConsentService:
    def __init__(
        self,
        repository: ConsentRepository,
        session_repository: CustomerSessionRepository,
        catalog: DemoConsentScopeCatalog,
    ) -> None:
        self.repository = repository
        self.session_repository = session_repository
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()
        self.catalog.initialize()

    def list_consents(self, session_id: str) -> ConsentListResponse:
        self._require_session(session_id)
        stored = {item.source_type: item for item in self.repository.list_consents(session_id)}
        consents = [
            self._current_or_pending(stored.get(definition.source_type), definition)
            for definition in self.catalog.scopes
        ]
        return ConsentListResponse(
            session_id=session_id,
            consents=consents,
            scope_version=self.catalog.data_version,
        )

    def _current_or_pending(
        self,
        stored: ConsentState | None,
        definition: ConsentScopeDefinition,
    ) -> ConsentState:
        if stored is not None and stored.scope_version == self.catalog.data_version:
            return stored
        return self._pending_state(definition)

    def grant_consent(
        self,
        session_id: str,
        source_type: str,
        request_id: str,
    ) -> ConsentState:
        self._require_session(session_id)
        definition = self._require_scope(source_type)
        existing = self.repository.get_consent(session_id, definition.source_type)
        if (
            existing is not None
            and existing.status == ConsentStatus.GRANTED
            and existing.scope_version == self.catalog.data_version
        ):
            return existing

        timestamp = datetime.now(UTC)
        state = ConsentState(
            source_type=definition.source_type,
            display_name=definition.display_name,
            description=definition.description,
            required=definition.required,
            status=ConsentStatus.GRANTED,
            granted_at=timestamp,
            updated_at=timestamp,
            scope_version=self.catalog.data_version,
        )
        return self._save(
            session_id=session_id,
            state=state,
            definition=definition,
            stage=AuditStage.CONSENT_GRANTED,
            request_id=request_id,
        )

    def withdraw_consent(
        self,
        session_id: str,
        source_type: str,
        request_id: str,
    ) -> ConsentState:
        self._require_session(session_id)
        definition = self._require_scope(source_type)
        existing = self.repository.get_consent(session_id, definition.source_type)
        if existing is None:
            raise ConsentNotGrantedError(source_type)
        if existing.status == ConsentStatus.WITHDRAWN:
            return existing

        timestamp = datetime.now(UTC)
        state = existing.model_copy(
            update={
                "status": ConsentStatus.WITHDRAWN,
                "withdrawn_at": timestamp,
                "updated_at": timestamp,
            }
        )
        return self._save(
            session_id=session_id,
            state=state,
            definition=definition,
            stage=AuditStage.CONSENT_WITHDRAWN,
            request_id=request_id,
        )

    def _require_session(self, session_id: str) -> None:
        if self.session_repository.get_session(session_id) is None:
            raise CustomerSessionNotFoundError(session_id)

    def _require_scope(self, source_type: str) -> ConsentScopeDefinition:
        definition = self.catalog.get(source_type)
        if definition is None:
            raise ConsentScopeNotFoundError(source_type)
        return definition

    def _pending_state(self, definition: ConsentScopeDefinition) -> ConsentState:
        return ConsentState(
            source_type=definition.source_type,
            display_name=definition.display_name,
            description=definition.description,
            required=definition.required,
            status=ConsentStatus.PENDING,
            scope_version=self.catalog.data_version,
        )

    def _save(
        self,
        *,
        session_id: str,
        state: ConsentState,
        definition: ConsentScopeDefinition,
        stage: AuditStage,
        request_id: str,
    ) -> ConsentState:
        snapshot = definition.model_dump(mode="json", by_alias=True)
        snapshot_json = json.dumps(
            snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=stage,
            timestamp=state.updated_at,
            actor=AuditActor.SYSTEM,
            input_version=self.catalog.data_version,
            input_snapshot_hash=hashlib.sha256(snapshot_json.encode()).hexdigest(),
            output_summary={
                "sourceType": state.source_type.value,
                "status": state.status.value,
                "demoOnly": state.demo_only,
            },
            data_version=self.catalog.data_version,
        )
        return self.repository.save_consent(
            session_id=session_id,
            state=state,
            audit_event=event,
        )

    def readiness(self) -> dict[str, bool]:
        return {
            "consent_repository": self.repository.is_ready(),
            "demo_consent_scopes": self.catalog.is_ready(),
        }
