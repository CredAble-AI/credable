import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.evidence_consent import EvidenceConsentState


class EvidenceConsentRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create storage for selection-scoped Evidence consent."""

    @abstractmethod
    def get_for_selection(
        self,
        session_id: str,
        selection_id: str,
    ) -> EvidenceConsentState | None:
        """Return the latest consent state for one session-owned selection."""

    @abstractmethod
    def save_consent(
        self,
        *,
        session_id: str,
        state: EvidenceConsentState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceConsentState:
        """Persist consent and its Audit event atomically."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteEvidenceConsentRepository(EvidenceConsentRepository):
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
                CREATE TABLE IF NOT EXISTS evidence_consents (
                    evidence_consent_id TEXT NOT NULL UNIQUE,
                    selection_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, selection_id),
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id),
                    FOREIGN KEY (selection_id) REFERENCES evidence_selections(selection_id)
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_consents_session
                ON evidence_consents(session_id);
                """
            )

    def get_for_selection(
        self,
        session_id: str,
        selection_id: str,
    ) -> EvidenceConsentState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM evidence_consents
                WHERE session_id = ? AND selection_id = ?
                """,
                (session_id, selection_id),
            ).fetchone()
        return EvidenceConsentState.model_validate_json(row["state_json"]) if row else None

    def save_consent(
        self,
        *,
        session_id: str,
        state: EvidenceConsentState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceConsentState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_consents(
                    evidence_consent_id,
                    selection_id,
                    session_id,
                    state_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, selection_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    state.evidence_consent_id,
                    state.selection_id,
                    session_id,
                    state.model_dump_json(by_alias=True),
                    audit_event.timestamp.isoformat(),
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

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM evidence_consents LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
