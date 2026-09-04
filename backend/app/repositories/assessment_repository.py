import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.assessment import AssessmentInputSnapshot, AssessmentState
from app.schemas.audit import SessionAuditEvent


class AssessmentRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_latest(self, session_id: str) -> AssessmentState | None:
        """Return the latest assessment execution for a session."""

    @abstractmethod
    def save_execution(
        self,
        *,
        session_id: str,
        state: AssessmentState,
        snapshot: AssessmentInputSnapshot,
        audit_event: SessionAuditEvent,
    ) -> AssessmentState:
        """Persist an execution, its input snapshot, and Audit atomically."""

    @abstractmethod
    def count_executions(self, session_id: str) -> int:
        """Return the number of preserved executions for a session."""

    @abstractmethod
    def get_snapshot(self, assessment_id: str) -> AssessmentInputSnapshot | None:
        """Return the fixed input snapshot for an assessment execution."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteAssessmentRepository(AssessmentRepository):
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
                CREATE TABLE IF NOT EXISTS customer_assessments (
                    execution_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    assessment_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    input_snapshot_json TEXT NOT NULL,
                    input_snapshot_hash TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_customer_assessments_latest
                ON customer_assessments(session_id, calculated_at DESC);
                """
            )

    def get_latest(self, session_id: str) -> AssessmentState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM customer_assessments
                WHERE session_id = ?
                ORDER BY execution_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return AssessmentState.model_validate_json(row["state_json"]) if row else None

    def save_execution(
        self,
        *,
        session_id: str,
        state: AssessmentState,
        snapshot: AssessmentInputSnapshot,
        audit_event: SessionAuditEvent,
    ) -> AssessmentState:
        if state.assessment_id is None or state.calculated_at is None:
            raise ValueError("assessment execution metadata is required")
        state_json = state.model_dump_json(by_alias=True)
        snapshot_json = snapshot.model_dump_json(by_alias=True)
        event_json = audit_event.model_dump_json(by_alias=True)
        timestamp = state.calculated_at.isoformat()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO customer_assessments(
                    assessment_id,
                    session_id,
                    state_json,
                    input_snapshot_json,
                    input_snapshot_hash,
                    calculated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    state.assessment_id,
                    session_id,
                    state_json,
                    snapshot_json,
                    audit_event.input_snapshot_hash,
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
                    session_id,
                    audit_event.timestamp.isoformat(),
                    event_json,
                ),
            )
        return state

    def count_executions(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM customer_assessments
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def get_snapshot(self, assessment_id: str) -> AssessmentInputSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT input_snapshot_json
                FROM customer_assessments
                WHERE assessment_id = ?
                """,
                (assessment_id,),
            ).fetchone()
        return (
            AssessmentInputSnapshot.model_validate_json(row["input_snapshot_json"]) if row else None
        )

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM customer_assessments LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
