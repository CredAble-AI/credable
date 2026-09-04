import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.consent import ConsentSourceType, ConsentState


class ConsentRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_consent(
        self,
        session_id: str,
        source_type: ConsentSourceType,
    ) -> ConsentState | None:
        """Return the latest stored state for one consent scope."""

    @abstractmethod
    def list_consents(self, session_id: str) -> list[ConsentState]:
        """Return stored consent states for a customer session."""

    @abstractmethod
    def save_consent(
        self,
        *,
        session_id: str,
        state: ConsentState,
        audit_event: SessionAuditEvent,
    ) -> ConsentState:
        """Persist consent state and its audit event atomically."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteConsentRepository(ConsentRepository):
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
                CREATE TABLE IF NOT EXISTS customer_consents (
                    session_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, source_type),
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_customer_consents_session
                ON customer_consents(session_id);
                """
            )

    def get_consent(
        self,
        session_id: str,
        source_type: ConsentSourceType,
    ) -> ConsentState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM customer_consents
                WHERE session_id = ? AND source_type = ?
                """,
                (session_id, source_type.value),
            ).fetchone()
        return ConsentState.model_validate_json(row["state_json"]) if row else None

    def list_consents(self, session_id: str) -> list[ConsentState]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT state_json
                FROM customer_consents
                WHERE session_id = ?
                ORDER BY source_type
                """,
                (session_id,),
            ).fetchall()
        return [ConsentState.model_validate_json(row["state_json"]) for row in rows]

    def save_consent(
        self,
        *,
        session_id: str,
        state: ConsentState,
        audit_event: SessionAuditEvent,
    ) -> ConsentState:
        state_json = state.model_dump_json(by_alias=True)
        event_json = audit_event.model_dump_json(by_alias=True)
        timestamp = audit_event.timestamp.isoformat()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO customer_consents(
                    session_id,
                    source_type,
                    state_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, source_type) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (session_id, state.source_type.value, state_json, timestamp),
            )
            connection.execute(
                """
                INSERT INTO customer_session_audit_events(
                    event_id,
                    session_id,
                    timestamp,
                    event_json
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    audit_event.event_id,
                    session_id,
                    timestamp,
                    event_json,
                ),
            )
        return state

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM customer_consents LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
