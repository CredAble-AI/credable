import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.evidence_submission import EvidenceSubmissionState


class EvidenceSubmissionRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_latest(self, session_id: str) -> EvidenceSubmissionState | None:
        """Return the latest Evidence submission for a session."""

    @abstractmethod
    def get_by_submission_id(self, submission_id: str) -> EvidenceSubmissionState | None:
        """Return an Evidence submission by its identifier."""

    @abstractmethod
    def get_by_selection_id(self, selection_id: str) -> EvidenceSubmissionState | None:
        """Return an existing submission for the same Evidence selection."""

    @abstractmethod
    def save_submission(
        self,
        *,
        session_id: str,
        state: EvidenceSubmissionState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceSubmissionState:
        """Persist one Evidence submission and its Audit atomically."""

    @abstractmethod
    def count_submissions(self, session_id: str) -> int:
        """Return the number of preserved submissions for a session."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteEvidenceSubmissionRepository(EvidenceSubmissionRepository):
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
                CREATE TABLE IF NOT EXISTS evidence_submissions (
                    submission_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id TEXT NOT NULL UNIQUE,
                    selection_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_submissions_latest
                ON evidence_submissions(session_id, submission_order DESC);
                """
            )

    def get_latest(self, session_id: str) -> EvidenceSubmissionState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM evidence_submissions
                WHERE session_id = ?
                ORDER BY submission_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return EvidenceSubmissionState.model_validate_json(row["state_json"]) if row else None

    def get_by_submission_id(self, submission_id: str) -> EvidenceSubmissionState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM evidence_submissions WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
        return EvidenceSubmissionState.model_validate_json(row["state_json"]) if row else None

    def get_by_selection_id(self, selection_id: str) -> EvidenceSubmissionState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM evidence_submissions WHERE selection_id = ?",
                (selection_id,),
            ).fetchone()
        return EvidenceSubmissionState.model_validate_json(row["state_json"]) if row else None

    def save_submission(
        self,
        *,
        session_id: str,
        state: EvidenceSubmissionState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceSubmissionState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_submissions(
                    submission_id,
                    selection_id,
                    session_id,
                    state_json,
                    submitted_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    state.submission_id,
                    state.selection_id,
                    session_id,
                    state.model_dump_json(by_alias=True),
                    state.submitted_at.isoformat(),
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

    def count_submissions(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM evidence_submissions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM evidence_submissions LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
