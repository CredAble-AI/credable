import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.evidence_quality import EvidenceQualityState, EvidenceQualityStatus


class EvidenceQualityRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_for_submission(
        self,
        session_id: str,
        submission_id: str,
    ) -> EvidenceQualityState | None:
        """Return the quality result for a submission in the session."""

    @abstractmethod
    def list_for_session(self, session_id: str) -> list[EvidenceQualityState]:
        """Return all Evidence quality results for a session in check order."""

    @abstractmethod
    def save_quality(
        self,
        *,
        session_id: str,
        state: EvidenceQualityState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceQualityState:
        """Persist one quality result and its Audit atomically."""

    @abstractmethod
    def count_checks(self, session_id: str) -> int:
        """Return the number of preserved quality checks for a session."""

    @abstractmethod
    def list_review_required(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[tuple[str, EvidenceQualityState]]:
        """Return one newest-first page of Evidence requiring human review."""

    @abstractmethod
    def count_review_required(self) -> int:
        """Return the total number of Evidence quality results requiring review."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteEvidenceQualityRepository(EvidenceQualityRepository):
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
                CREATE TABLE IF NOT EXISTS evidence_quality_checks (
                    check_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    quality_check_id TEXT NOT NULL UNIQUE,
                    submission_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    FOREIGN KEY (submission_id) REFERENCES evidence_submissions(submission_id),
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_quality_checks_session
                ON evidence_quality_checks(session_id, check_order DESC);
                """
            )

    def get_for_submission(
        self,
        session_id: str,
        submission_id: str,
    ) -> EvidenceQualityState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM evidence_quality_checks
                WHERE session_id = ? AND submission_id = ?
                """,
                (session_id, submission_id),
            ).fetchone()
        return EvidenceQualityState.model_validate_json(row["state_json"]) if row else None

    def list_for_session(self, session_id: str) -> list[EvidenceQualityState]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT state_json
                FROM evidence_quality_checks
                WHERE session_id = ?
                ORDER BY check_order ASC
                """,
                (session_id,),
            ).fetchall()
        return [EvidenceQualityState.model_validate_json(row["state_json"]) for row in rows]

    def save_quality(
        self,
        *,
        session_id: str,
        state: EvidenceQualityState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceQualityState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_quality_checks(
                    quality_check_id,
                    submission_id,
                    session_id,
                    state_json,
                    checked_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    state.quality_check_id,
                    state.submission_id,
                    session_id,
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
                "SELECT COUNT(*) AS count FROM evidence_quality_checks WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def list_review_required(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[tuple[str, EvidenceQualityState]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, state_json
                FROM evidence_quality_checks
                WHERE json_extract(state_json, '$.status') = ?
                ORDER BY check_order DESC
                LIMIT ? OFFSET ?
                """,
                (EvidenceQualityStatus.REVIEW_REQUIRED.value, limit, offset),
            ).fetchall()
        return [
            (row["session_id"], EvidenceQualityState.model_validate_json(row["state_json"]))
            for row in rows
        ]

    def count_review_required(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM evidence_quality_checks
                WHERE json_extract(state_json, '$.status') = ?
                """,
                (EvidenceQualityStatus.REVIEW_REQUIRED.value,),
            ).fetchone()
        return int(row["count"])

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM evidence_quality_checks LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
