import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.product_condition import (
    ProductConditionInputSnapshot,
    ProductConditionQueryState,
)


class ProductConditionRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_latest(self, session_id: str) -> ProductConditionQueryState | None:
        """Return the latest condition query for a session."""

    @abstractmethod
    def save_query(
        self,
        *,
        session_id: str,
        state: ProductConditionQueryState,
        snapshot: ProductConditionInputSnapshot | None,
        audit_event: SessionAuditEvent,
    ) -> ProductConditionQueryState:
        """Persist a query, its available inputs, and Audit atomically."""

    @abstractmethod
    def count_queries(self, session_id: str) -> int:
        """Return the number of preserved queries for a session."""

    @abstractmethod
    def get_snapshot(self, query_id: str) -> ProductConditionInputSnapshot | None:
        """Return the fixed input snapshot for a condition query."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteProductConditionRepository(ProductConditionRepository):
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
                CREATE TABLE IF NOT EXISTS product_condition_queries (
                    query_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    input_snapshot_json TEXT,
                    input_snapshot_hash TEXT NOT NULL,
                    queried_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_product_condition_latest
                ON product_condition_queries(session_id, query_order DESC);
                """
            )

    def get_latest(self, session_id: str) -> ProductConditionQueryState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM product_condition_queries
                WHERE session_id = ?
                ORDER BY query_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return ProductConditionQueryState.model_validate_json(row["state_json"]) if row else None

    def save_query(
        self,
        *,
        session_id: str,
        state: ProductConditionQueryState,
        snapshot: ProductConditionInputSnapshot | None,
        audit_event: SessionAuditEvent,
    ) -> ProductConditionQueryState:
        if state.query_id is None or state.queried_at is None:
            raise ValueError("product condition query metadata is required")
        state_json = state.model_dump_json(by_alias=True)
        snapshot_json = snapshot.model_dump_json(by_alias=True) if snapshot else None
        event_json = audit_event.model_dump_json(by_alias=True)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO product_condition_queries(
                    query_id,
                    session_id,
                    state_json,
                    input_snapshot_json,
                    input_snapshot_hash,
                    queried_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    state.query_id,
                    session_id,
                    state_json,
                    snapshot_json,
                    audit_event.input_snapshot_hash,
                    state.queried_at.isoformat(),
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

    def count_queries(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM product_condition_queries
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def get_snapshot(self, query_id: str) -> ProductConditionInputSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT input_snapshot_json
                FROM product_condition_queries
                WHERE query_id = ?
                """,
                (query_id,),
            ).fetchone()
        if row is None or row["input_snapshot_json"] is None:
            return None
        return ProductConditionInputSnapshot.model_validate_json(row["input_snapshot_json"])

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM product_condition_queries LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
