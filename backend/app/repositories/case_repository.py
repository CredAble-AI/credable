import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import AuditEvent
from app.schemas.case import CaseState


class CaseRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_case(self, case_id: str) -> CaseState | None:
        """Return a Case state by its stable identifier."""

    @abstractmethod
    def get_case_by_demo_id(self, demo_case_id: str) -> CaseState | None:
        """Return the Case previously created from a demo fixture."""

    @abstractmethod
    def create_demo_case(
        self,
        *,
        demo_case_id: str,
        state: CaseState,
        audit_event: AuditEvent,
    ) -> CaseState:
        """Persist a demo Case and its creation event atomically."""

    @abstractmethod
    def list_audit_events(self, case_id: str) -> list[AuditEvent]:
        """Return stored audit events in creation order."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteCaseRepository(CaseRepository):
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    demo_case_id TEXT NOT NULL UNIQUE,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES cases(case_id)
                );

                CREATE INDEX IF NOT EXISTS idx_audit_events_case_timestamp
                ON audit_events(case_id, timestamp);
                """
            )

    def get_case(self, case_id: str) -> CaseState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        return CaseState.model_validate_json(row["state_json"]) if row else None

    def get_case_by_demo_id(self, demo_case_id: str) -> CaseState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM cases WHERE demo_case_id = ?",
                (demo_case_id,),
            ).fetchone()
        return CaseState.model_validate_json(row["state_json"]) if row else None

    def create_demo_case(
        self,
        *,
        demo_case_id: str,
        state: CaseState,
        audit_event: AuditEvent,
    ) -> CaseState:
        state_json = state.model_dump_json(by_alias=True)
        event_json = audit_event.model_dump_json(by_alias=True)
        timestamp = audit_event.timestamp.isoformat()

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO cases(case_id, demo_case_id, state_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (state.case.case_id, demo_case_id, state_json, timestamp, timestamp),
                )
                connection.execute(
                    """
                    INSERT INTO audit_events(event_id, case_id, timestamp, event_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (audit_event.event_id, state.case.case_id, timestamp, event_json),
                )
        except sqlite3.IntegrityError:
            existing = self.get_case_by_demo_id(demo_case_id)
            if existing is None:
                raise
            return existing

        return state

    def list_audit_events(self, case_id: str) -> list[AuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json
                FROM audit_events
                WHERE case_id = ?
                ORDER BY timestamp, event_id
                """,
                (case_id,),
            ).fetchall()
        return [AuditEvent.model_validate_json(row["event_json"]) for row in rows]

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM cases LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
