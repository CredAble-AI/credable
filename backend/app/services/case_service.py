import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import CaseNotFoundError, DemoCaseNotFoundError
from app.repositories.case_repository import CaseRepository
from app.schemas.audit import AuditActor, AuditEvent, AuditStage
from app.schemas.case import CaseState, DemoCaseCatalogData, DemoCaseDefinition


class DemoCaseCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoCaseCatalogData | None = None
        self._cases_by_id: dict[str, DemoCaseDefinition] = {}

    def initialize(self) -> None:
        catalog = DemoCaseCatalogData.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        cases_by_id = {item.demo_case_id: item for item in catalog.cases}
        if len(cases_by_id) != len(catalog.cases):
            raise ValueError("demoCaseId values must be unique")
        self._catalog = catalog
        self._cases_by_id = cases_by_id

    @property
    def data_version(self) -> str:
        if self._catalog is None:
            raise RuntimeError("Demo Case catalog is not initialized")
        return self._catalog.data_version

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(self._cases_by_id)

    def get(self, demo_case_id: str) -> DemoCaseDefinition | None:
        return self._cases_by_id.get(demo_case_id)

    def is_ready(self) -> bool:
        return self._catalog is not None and bool(self._cases_by_id)


class CaseService:
    def __init__(self, repository: CaseRepository, catalog: DemoCaseCatalog) -> None:
        self.repository = repository
        self.catalog = catalog

    def initialize(self) -> None:
        self.repository.initialize()
        self.catalog.initialize()

    def create_demo_case(self, demo_case_id: str, request_id: str) -> CaseState:
        existing = self.repository.get_case_by_demo_id(demo_case_id)
        if existing is not None:
            return existing

        definition = self.catalog.get(demo_case_id)
        if definition is None:
            raise DemoCaseNotFoundError(demo_case_id)

        state = CaseState(case=definition.case)
        snapshot = definition.case.model_dump(mode="json", by_alias=True)
        snapshot_json = json.dumps(
            snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
        timestamp = datetime.now(UTC)
        audit_event = AuditEvent(
            event_id=f"evt_{uuid4().hex}",
            case_id=definition.case.case_id,
            request_id=request_id,
            stage=AuditStage.CASE_CREATED,
            timestamp=timestamp,
            actor=AuditActor.SYSTEM,
            input_version=self.catalog.data_version,
            input_snapshot_hash=snapshot_hash,
            output_summary={
                "demoCaseId": demo_case_id,
                "demoOnly": definition.case.demo_only,
            },
            data_version=self.catalog.data_version,
        )
        return self.repository.create_demo_case(
            demo_case_id=demo_case_id,
            state=state,
            audit_event=audit_event,
        )

    def get_case(self, case_id: str) -> CaseState:
        state = self.repository.get_case(case_id)
        if state is None:
            raise CaseNotFoundError(case_id)
        return state

    def readiness(self) -> dict[str, bool]:
        return {
            "repository": self.repository.is_ready(),
            "demo_cases": self.catalog.is_ready(),
        }
