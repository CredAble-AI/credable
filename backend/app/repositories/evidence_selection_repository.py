import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.evidence_selection import EvidenceSelectionState


class EvidenceSelectionRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_latest(self, session_id: str) -> EvidenceSelectionState | None:
        """Return the latest evidence selection for a session."""

    @abstractmethod
    def get_by_boundary_check_id(
        self,
        boundary_check_id: str,
    ) -> EvidenceSelectionState | None:
        """Return an existing selection for the same boundary decision."""

    @abstractmethod
    def save_selection(
        self,
        *,
        session_id: str,
        state: EvidenceSelectionState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceSelectionState:
        """Persist one selection and its Audit atomically."""

    @abstractmethod
    def count_selections(self, session_id: str) -> int:
        """Return the number of preserved selections for a session."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteEvidenceSelectionRepository(EvidenceSelectionRepository):
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
                CREATE TABLE IF NOT EXISTS evidence_selections (
                    selection_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    selection_id TEXT NOT NULL UNIQUE,
                    boundary_check_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    selected_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_selections_latest
                ON evidence_selections(session_id, selection_order DESC);
                """
            )

    def get_latest(self, session_id: str) -> EvidenceSelectionState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM evidence_selections
                WHERE session_id = ?
                ORDER BY selection_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return EvidenceSelectionState.model_validate_json(row["state_json"]) if row else None

    def get_by_boundary_check_id(
        self,
        boundary_check_id: str,
    ) -> EvidenceSelectionState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM evidence_selections WHERE boundary_check_id = ?",
                (boundary_check_id,),
            ).fetchone()
        return EvidenceSelectionState.model_validate_json(row["state_json"]) if row else None

    def save_selection(
        self,
        *,
        session_id: str,
        state: EvidenceSelectionState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceSelectionState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_selections(
                    selection_id,
                    boundary_check_id,
                    session_id,
                    state_json,
                    selected_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    state.selection_id,
                    state.boundary_check_id,
                    session_id,
                    state.model_dump_json(by_alias=True),
                    state.selected_at.isoformat(),
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

    def count_selections(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM evidence_selections WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM evidence_selections LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
