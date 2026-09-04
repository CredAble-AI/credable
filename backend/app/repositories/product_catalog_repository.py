import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.product import ProductCatalogState


class ProductCatalogRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_latest(self, session_id: str) -> ProductCatalogState | None:
        """Return the latest catalog snapshot for a session."""

    @abstractmethod
    def save_snapshot(
        self,
        *,
        session_id: str,
        state: ProductCatalogState,
        audit_event: SessionAuditEvent,
    ) -> ProductCatalogState:
        """Persist a catalog snapshot and its Audit atomically."""

    @abstractmethod
    def count_snapshots(self, session_id: str) -> int:
        """Return the number of preserved catalog refreshes."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteProductCatalogRepository(ProductCatalogRepository):
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
                CREATE TABLE IF NOT EXISTS product_catalog_snapshots (
                    snapshot_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    catalog_snapshot_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_product_catalog_latest
                ON product_catalog_snapshots(session_id, snapshot_order DESC);
                """
            )

    def get_latest(self, session_id: str) -> ProductCatalogState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM product_catalog_snapshots
                WHERE session_id = ?
                ORDER BY snapshot_order DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return ProductCatalogState.model_validate_json(row["state_json"]) if row else None

    def save_snapshot(
        self,
        *,
        session_id: str,
        state: ProductCatalogState,
        audit_event: SessionAuditEvent,
    ) -> ProductCatalogState:
        if state.catalog_snapshot_id is None or state.retrieved_at is None:
            raise ValueError("catalog snapshot metadata is required")
        state_json = state.model_dump_json(by_alias=True)
        event_json = audit_event.model_dump_json(by_alias=True)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO product_catalog_snapshots(
                    catalog_snapshot_id,
                    session_id,
                    state_json,
                    retrieved_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    state.catalog_snapshot_id,
                    session_id,
                    state_json,
                    state.retrieved_at.isoformat(),
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

    def count_snapshots(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM product_catalog_snapshots
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return int(row["count"])

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM product_catalog_snapshots LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
