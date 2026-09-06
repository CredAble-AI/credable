import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.assessment_review import AssessmentReviewRequestState
from app.schemas.audit import SessionAuditEvent


class AssessmentReviewRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create storage for customer assessment review requests."""

    @abstractmethod
    def get_latest(self, session_id: str) -> AssessmentReviewRequestState | None:
        """Return the latest customer review request for a session."""

    @abstractmethod
    def get_for_target(
        self,
        session_id: str,
        target_assessment_id: str,
    ) -> AssessmentReviewRequestState | None:
        """Return an idempotent request for one assessment target."""

    @abstractmethod
    def list_latest(self, *, limit: int) -> list[tuple[str, AssessmentReviewRequestState]]:
        """Return newest customer review requests with their session IDs."""

    @abstractmethod
    def count(self) -> int:
        """Return the number of customer review requests."""

    @abstractmethod
    def save(
        self,
        *,
        session_id: str,
        state: AssessmentReviewRequestState,
        audit_event: SessionAuditEvent,
    ) -> AssessmentReviewRequestState:
        """Persist a review request and Audit atomically."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether review request storage can be queried."""


class SqliteAssessmentReviewRepository(AssessmentReviewRepository):
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
                CREATE TABLE IF NOT EXISTS assessment_review_requests (
                    request_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_request_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    target_assessment_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    UNIQUE(session_id, target_assessment_id),
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_assessment_review_requests_latest
                ON assessment_review_requests(request_order DESC);
                """
            )

    def get_latest(self, session_id: str) -> AssessmentReviewRequestState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM assessment_review_requests
                WHERE session_id = ?
                ORDER BY request_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return AssessmentReviewRequestState.model_validate_json(row["state_json"]) if row else None

    def get_for_target(
        self,
        session_id: str,
        target_assessment_id: str,
    ) -> AssessmentReviewRequestState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM assessment_review_requests
                WHERE session_id = ? AND target_assessment_id = ?
                """,
                (session_id, target_assessment_id),
            ).fetchone()
        return AssessmentReviewRequestState.model_validate_json(row["state_json"]) if row else None

    def list_latest(self, *, limit: int) -> list[tuple[str, AssessmentReviewRequestState]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, state_json
                FROM assessment_review_requests
                ORDER BY request_order DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            (row["session_id"], AssessmentReviewRequestState.model_validate_json(row["state_json"]))
            for row in rows
        ]

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM assessment_review_requests"
            ).fetchone()
        return int(row["count"])

    def save(
        self,
        *,
        session_id: str,
        state: AssessmentReviewRequestState,
        audit_event: SessionAuditEvent,
    ) -> AssessmentReviewRequestState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assessment_review_requests(
                    review_request_id,
                    session_id,
                    target_assessment_id,
                    state_json,
                    requested_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    state.review_request_id,
                    session_id,
                    state.target_assessment_id,
                    state.model_dump_json(by_alias=True),
                    state.requested_at.isoformat(),
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
                connection.execute("SELECT 1 FROM assessment_review_requests LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
