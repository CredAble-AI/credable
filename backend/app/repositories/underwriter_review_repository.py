import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.review_workflow import UnderwriterReviewWorkflowState


class UnderwriterReviewRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create storage for persisted underwriter processing states."""

    @abstractmethod
    def get(self, review_id: str) -> UnderwriterReviewWorkflowState | None:
        """Return a persisted review processing state."""

    @abstractmethod
    def list_all(self) -> list[UnderwriterReviewWorkflowState]:
        """Return all persisted review processing states."""

    @abstractmethod
    def save_started(
        self,
        *,
        state: UnderwriterReviewWorkflowState,
        audit_event: SessionAuditEvent,
    ) -> UnderwriterReviewWorkflowState:
        """Persist the first transition to IN_REVIEW and its Audit atomically."""

    @abstractmethod
    def save_completed(
        self,
        *,
        state: UnderwriterReviewWorkflowState,
        audit_event: SessionAuditEvent,
    ) -> UnderwriterReviewWorkflowState:
        """Persist the transition to COMPLETED and its Audit atomically."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the Workflow repository can be queried."""


class SqliteUnderwriterReviewRepository(UnderwriterReviewRepository):
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
                CREATE TABLE IF NOT EXISTS underwriter_review_workflows (
                    review_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_id TEXT NOT NULL UNIQUE,
                    state_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_underwriter_review_workflows_status
                ON underwriter_review_workflows(completed_at, started_at DESC);
                """
            )

    def get(self, review_id: str) -> UnderwriterReviewWorkflowState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM underwriter_review_workflows
                WHERE review_id = ?
                """,
                (review_id,),
            ).fetchone()
        return (
            UnderwriterReviewWorkflowState.model_validate_json(row["state_json"]) if row else None
        )

    def list_all(self) -> list[UnderwriterReviewWorkflowState]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT state_json
                FROM underwriter_review_workflows
                ORDER BY started_at DESC
                """
            ).fetchall()
        return [
            UnderwriterReviewWorkflowState.model_validate_json(row["state_json"]) for row in rows
        ]

    def save_started(
        self,
        *,
        state: UnderwriterReviewWorkflowState,
        audit_event: SessionAuditEvent,
    ) -> UnderwriterReviewWorkflowState:
        if state.started_at is None:
            raise ValueError("started review requires startedAt")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO underwriter_review_workflows(
                        review_id,
                        session_id,
                        trigger_type,
                        trigger_id,
                        state_json,
                        started_at,
                        completed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        state.review_id,
                        state.session_id,
                        state.trigger_type,
                        state.trigger_id,
                        state.model_dump_json(by_alias=True),
                        state.started_at.isoformat(),
                    ),
                )
                self._insert_audit(connection, audit_event)
        except sqlite3.IntegrityError:
            existing = self.get(state.review_id)
            if existing is not None:
                return existing
            raise
        return state

    def save_completed(
        self,
        *,
        state: UnderwriterReviewWorkflowState,
        audit_event: SessionAuditEvent,
    ) -> UnderwriterReviewWorkflowState:
        if state.completed_at is None:
            raise ValueError("completed review requires completedAt")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE underwriter_review_workflows
                SET state_json = ?, completed_at = ?
                WHERE review_id = ? AND completed_at IS NULL
                """,
                (
                    state.model_dump_json(by_alias=True),
                    state.completed_at.isoformat(),
                    state.review_id,
                ),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    """
                    SELECT state_json
                    FROM underwriter_review_workflows
                    WHERE review_id = ?
                    """,
                    (state.review_id,),
                ).fetchone()
                if row is not None:
                    return UnderwriterReviewWorkflowState.model_validate_json(row["state_json"])
                raise ValueError("review Workflow must be started before completion")
            self._insert_audit(connection, audit_event)
        return state

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM underwriter_review_workflows LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True

    @staticmethod
    def _insert_audit(
        connection: sqlite3.Connection,
        audit_event: SessionAuditEvent,
    ) -> None:
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
                audit_event.session_id,
                audit_event.timestamp.isoformat(),
                audit_event.model_dump_json(by_alias=True),
            ),
        )
