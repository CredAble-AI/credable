import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.policy_boundary import (
    BoundaryStatus,
    EvidenceResolutionState,
    EvidenceResolutionStatus,
    PolicyBoundaryCheckState,
)


class PolicyBoundaryRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_latest(self, session_id: str) -> PolicyBoundaryCheckState | None:
        """Return the latest policy boundary check for a session."""

    @abstractmethod
    def get_check_by_id(
        self,
        boundary_check_id: str,
    ) -> tuple[str, PolicyBoundaryCheckState] | None:
        """Return a policy boundary check with its owning session."""

    @abstractmethod
    def list_policy_blocked(self) -> list[tuple[str, PolicyBoundaryCheckState]]:
        """Return policy boundary checks requiring underwriter review."""

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
    def get_latest_resolution(self, session_id: str) -> EvidenceResolutionState | None:
        """Return the latest Evidence resolution for a session."""

    @abstractmethod
    def get_resolution_by_id(
        self,
        resolution_id: str,
    ) -> tuple[str, EvidenceResolutionState] | None:
        """Return an Evidence resolution with its owning session."""

    @abstractmethod
    def list_human_review_resolutions(self) -> list[tuple[str, EvidenceResolutionState]]:
        """Return Evidence resolutions requiring underwriter review."""

    @abstractmethod
    def get_resolution_by_comparison_id(
        self,
        comparison_id: str,
    ) -> EvidenceResolutionState | None:
        """Return an existing resolution for an assessment comparison."""

    @abstractmethod
    def save_resolution(
        self,
        *,
        session_id: str,
        state: EvidenceResolutionState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceResolutionState:
        """Persist an Evidence resolution and its Audit atomically."""

    @abstractmethod
    def count_resolutions(self, session_id: str) -> int:
        """Return the number of Evidence resolutions for a session."""

    @abstractmethod
    def is_resolution_ready(self) -> bool:
        """Report whether Evidence resolution storage can be queried."""

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

                CREATE TABLE IF NOT EXISTS evidence_collection_resolutions (
                    resolution_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    resolution_id TEXT NOT NULL UNIQUE,
                    comparison_id TEXT NOT NULL UNIQUE,
                    supplemental_assessment_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    resolved_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id),
                    FOREIGN KEY (comparison_id)
                        REFERENCES assessment_comparisons(comparison_id),
                    FOREIGN KEY (supplemental_assessment_id)
                        REFERENCES supplemental_assessments(supplemental_assessment_id)
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_collection_resolutions_latest
                ON evidence_collection_resolutions(session_id, resolution_order DESC);
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

    def get_check_by_id(
        self,
        boundary_check_id: str,
    ) -> tuple[str, PolicyBoundaryCheckState] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, state_json
                FROM policy_boundary_checks
                WHERE boundary_check_id = ?
                """,
                (boundary_check_id,),
            ).fetchone()
        if row is None:
            return None
        return row["session_id"], PolicyBoundaryCheckState.model_validate_json(row["state_json"])

    def list_policy_blocked(self) -> list[tuple[str, PolicyBoundaryCheckState]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, state_json
                FROM policy_boundary_checks
                ORDER BY check_order DESC
                """
            ).fetchall()
        items = [
            (row["session_id"], PolicyBoundaryCheckState.model_validate_json(row["state_json"]))
            for row in rows
        ]
        return [
            item
            for item in items
            if item[1].decision.status == BoundaryStatus.POLICY_BLOCKED
            and item[1].decision.underwriter_required
        ]

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

    def get_latest_resolution(self, session_id: str) -> EvidenceResolutionState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM evidence_collection_resolutions
                WHERE session_id = ?
                ORDER BY resolution_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return EvidenceResolutionState.model_validate_json(row["state_json"]) if row else None

    def get_resolution_by_id(
        self,
        resolution_id: str,
    ) -> tuple[str, EvidenceResolutionState] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, state_json
                FROM evidence_collection_resolutions
                WHERE resolution_id = ?
                """,
                (resolution_id,),
            ).fetchone()
        if row is None:
            return None
        return row["session_id"], EvidenceResolutionState.model_validate_json(row["state_json"])

    def list_human_review_resolutions(self) -> list[tuple[str, EvidenceResolutionState]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, state_json
                FROM evidence_collection_resolutions
                ORDER BY resolution_order DESC
                """
            ).fetchall()
        items = [
            (row["session_id"], EvidenceResolutionState.model_validate_json(row["state_json"]))
            for row in rows
        ]
        return [
            item
            for item in items
            if item[1].status == EvidenceResolutionStatus.HUMAN_REVIEW
            and item[1].underwriter_required
        ]

    def get_resolution_by_comparison_id(
        self,
        comparison_id: str,
    ) -> EvidenceResolutionState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM evidence_collection_resolutions
                WHERE comparison_id = ?
                """,
                (comparison_id,),
            ).fetchone()
        return EvidenceResolutionState.model_validate_json(row["state_json"]) if row else None

    def save_resolution(
        self,
        *,
        session_id: str,
        state: EvidenceResolutionState,
        audit_event: SessionAuditEvent,
    ) -> EvidenceResolutionState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_collection_resolutions(
                    resolution_id,
                    comparison_id,
                    supplemental_assessment_id,
                    session_id,
                    state_json,
                    resolved_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    state.resolution_id,
                    state.comparison_id,
                    state.supplemental_assessment_id,
                    session_id,
                    state.model_dump_json(by_alias=True),
                    state.resolved_at.isoformat(),
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

    def count_resolutions(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM evidence_collection_resolutions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def is_resolution_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    "SELECT 1 FROM evidence_collection_resolutions LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            return False
        return True

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM policy_boundary_checks LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
