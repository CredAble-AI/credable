import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.explanation import (
    AssessmentExplanationInputSnapshot,
    AssessmentExplanationState,
)


class AssessmentExplanationRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create storage for assessment explanations."""

    @abstractmethod
    def get_latest(self, session_id: str) -> AssessmentExplanationState | None:
        """Return the latest generated explanation for a session."""

    @abstractmethod
    def get_by_input_snapshot_hash(
        self,
        session_id: str,
        input_snapshot_hash: str,
    ) -> AssessmentExplanationState | None:
        """Return the idempotent explanation for one fixed input snapshot."""

    @abstractmethod
    def save(
        self,
        *,
        session_id: str,
        state: AssessmentExplanationState,
        snapshot: AssessmentExplanationInputSnapshot,
        audit_event: SessionAuditEvent,
    ) -> AssessmentExplanationState:
        """Persist an explanation, its input snapshot, and Audit atomically."""

    @abstractmethod
    def count(self, session_id: str) -> int:
        """Return the number of explanations generated for a session."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether explanation storage can be queried."""


class SqliteAssessmentExplanationRepository(AssessmentExplanationRepository):
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
                CREATE TABLE IF NOT EXISTS assessment_explanations (
                    explanation_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    explanation_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    target_assessment_id TEXT NOT NULL,
                    input_snapshot_hash TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    input_snapshot_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    UNIQUE(session_id, input_snapshot_hash),
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_assessment_explanations_latest
                ON assessment_explanations(session_id, explanation_order DESC);
                """
            )

    def get_latest(self, session_id: str) -> AssessmentExplanationState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM assessment_explanations
                WHERE session_id = ?
                ORDER BY explanation_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return AssessmentExplanationState.model_validate_json(row["state_json"]) if row else None

    def get_by_input_snapshot_hash(
        self,
        session_id: str,
        input_snapshot_hash: str,
    ) -> AssessmentExplanationState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM assessment_explanations
                WHERE session_id = ? AND input_snapshot_hash = ?
                """,
                (session_id, input_snapshot_hash),
            ).fetchone()
        return AssessmentExplanationState.model_validate_json(row["state_json"]) if row else None

    def save(
        self,
        *,
        session_id: str,
        state: AssessmentExplanationState,
        snapshot: AssessmentExplanationInputSnapshot,
        audit_event: SessionAuditEvent,
    ) -> AssessmentExplanationState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assessment_explanations(
                    explanation_id,
                    session_id,
                    target_assessment_id,
                    input_snapshot_hash,
                    state_json,
                    input_snapshot_json,
                    generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.explanation_id,
                    session_id,
                    state.target_assessment_id,
                    state.input_snapshot_hash,
                    state.model_dump_json(by_alias=True),
                    snapshot.model_dump_json(by_alias=True),
                    state.generated_at.isoformat(),
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

    def count(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM assessment_explanations WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM assessment_explanations LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
