import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.session import CustomerSessionState


class CustomerSessionRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_session(self, session_id: str) -> CustomerSessionState | None:
        """Return a customer session by its stable identifier."""

    @abstractmethod
    def create_session(
        self,
        *,
        state: CustomerSessionState,
        audit_event: SessionAuditEvent,
    ) -> CustomerSessionState:
        """Persist a new customer session and its creation event atomically."""

    @abstractmethod
    def list_audit_events(self, session_id: str) -> list[SessionAuditEvent]:
        """Return stored audit events in creation order."""

    @abstractmethod
    def list_audit_events_page(
        self,
        session_id: str,
        *,
        before_timestamp: datetime | None,
        before_event_id: str | None,
        limit: int,
    ) -> list[SessionAuditEvent]:
        """Return one newest-first page of stored audit events."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteCustomerSessionRepository(CustomerSessionRepository):
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
                CREATE TABLE IF NOT EXISTS customer_sessions (
                    session_id TEXT PRIMARY KEY,
                    demo_profile_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS customer_session_audit_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_customer_session_audit_timestamp
                ON customer_session_audit_events(session_id, timestamp);
                """
            )

    def get_session(self, session_id: str) -> CustomerSessionState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM customer_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return CustomerSessionState.model_validate_json(row["state_json"]) if row else None

    def create_session(
        self,
        *,
        state: CustomerSessionState,
        audit_event: SessionAuditEvent,
    ) -> CustomerSessionState:
        state_json = state.model_dump_json(by_alias=True)
        event_json = audit_event.model_dump_json(by_alias=True)
        timestamp = audit_event.timestamp.isoformat()
        session = state.session

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO customer_sessions(
                    session_id,
                    demo_profile_id,
                    state_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.demo_profile.demo_profile_id,
                    state_json,
                    timestamp,
                    timestamp,
                ),
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
                    session.session_id,
                    timestamp,
                    event_json,
                ),
            )
        return state

    def list_audit_events(self, session_id: str) -> list[SessionAuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json
                FROM customer_session_audit_events
                WHERE session_id = ?
                ORDER BY timestamp, event_id
                """,
                (session_id,),
            ).fetchall()
        return [SessionAuditEvent.model_validate_json(row["event_json"]) for row in rows]

    def list_audit_events_page(
        self,
        session_id: str,
        *,
        before_timestamp: datetime | None,
        before_event_id: str | None,
        limit: int,
    ) -> list[SessionAuditEvent]:
        if (before_timestamp is None) != (before_event_id is None):
            raise ValueError("audit cursor fields must be provided together")

        parameters: list[str | int] = [session_id]
        cursor_condition = ""
        if before_timestamp is not None and before_event_id is not None:
            cursor_condition = """
                AND (timestamp < ? OR (timestamp = ? AND event_id < ?))
            """
            encoded_timestamp = before_timestamp.isoformat()
            parameters.extend([encoded_timestamp, encoded_timestamp, before_event_id])
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT event_json
                FROM customer_session_audit_events
                WHERE session_id = ?
                {cursor_condition}
                ORDER BY timestamp DESC, event_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [SessionAuditEvent.model_validate_json(row["event_json"]) for row in rows]

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM customer_sessions LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
