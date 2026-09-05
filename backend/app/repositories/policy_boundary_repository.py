import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.policy_boundary import PolicyBoundaryCheckState


class PolicyBoundaryRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_latest(self, session_id: str) -> PolicyBoundaryCheckState | None:
        """Return the latest policy boundary check for a session."""

    @abstractmethod
    def save_check(
        self,
        *,
        session_id: str,
        state: PolicyBoundaryCheckState,
        audit_event: SessionAuditEvent,
    ) -> PolicyBoundaryCheckState:
        """Persist a boundary check and its Audit atomically."""

    @abstractmethod
    def count_checks(self, session_id: str) -> int:
        """Return the number of preserved checks for a session."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqlitePolicyBoundaryRepository(PolicyBoundaryRepository):
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
                CREATE TABLE IF NOT EXISTS policy_boundary_checks (
                    check_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    boundary_check_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    assessment_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_policy_boundary_checks_latest
                ON policy_boundary_checks(session_id, check_order DESC);
                """
            )

    def get_latest(self, session_id: str) -> PolicyBoundaryCheckState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM policy_boundary_checks
                WHERE session_id = ?
                ORDER BY check_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return PolicyBoundaryCheckState.model_validate_json(row["state_json"]) if row else None

    def save_check(
        self,
        *,
        session_id: str,
        state: PolicyBoundaryCheckState,
        audit_event: SessionAuditEvent,
    ) -> PolicyBoundaryCheckState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO policy_boundary_checks(
                    boundary_check_id,
                    session_id,
                    assessment_id,
                    state_json,
                    checked_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    state.boundary_check_id,
                    session_id,
                    state.assessment_id,
                    state.model_dump_json(by_alias=True),
                    state.checked_at.isoformat(),
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
                    session_id,
                    audit_event.timestamp.isoformat(),
                    audit_event.model_dump_json(by_alias=True),
                ),
            )
        return state

    def count_checks(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM policy_boundary_checks WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM policy_boundary_checks LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
