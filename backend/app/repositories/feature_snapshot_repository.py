import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.assessment import AssessmentDataSnapshotReference, AssessmentSnapshotType
from app.schemas.feature_snapshot import (
    AssessmentFeatureSnapshot,
    FeatureCode,
    FeatureValueStatus,
    FeatureValueType,
    NeutralFeatureValue,
)


class FeatureSnapshotRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create immutable feature-snapshot storage."""

    @abstractmethod
    def save(self, snapshot: AssessmentFeatureSnapshot) -> AssessmentFeatureSnapshot:
        """Persist one feature snapshot without replacing an existing version."""

    @abstractmethod
    def get(self, feature_snapshot_id: str) -> AssessmentFeatureSnapshot | None:
        """Restore a feature snapshot by its deterministic identifier."""

    @abstractmethod
    def get_by_lineage(
        self,
        session_id: str,
        feature_set_version: str,
        source_lineage_hash: str,
    ) -> AssessmentFeatureSnapshot | None:
        """Restore the feature snapshot derived from the same source lineage."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether feature snapshot storage can be queried."""


class SqliteFeatureSnapshotRepository(FeatureSnapshotRepository):
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
                CREATE TABLE IF NOT EXISTS assessment_feature_snapshots (
                    feature_snapshot_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    feature_set_version TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    source_lineage_hash TEXT NOT NULL,
                    source_snapshots_json TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    UNIQUE (session_id, feature_set_version, source_lineage_hash),
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS assessment_feature_values (
                    feature_snapshot_id TEXT NOT NULL,
                    feature_code TEXT NOT NULL,
                    dimension_key TEXT NOT NULL,
                    source_snapshot_type TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    numeric_value TEXT,
                    currency TEXT,
                    calculation_version TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    PRIMARY KEY (feature_snapshot_id, feature_code, dimension_key),
                    FOREIGN KEY (feature_snapshot_id)
                        REFERENCES assessment_feature_snapshots(feature_snapshot_id)
                );
                """
            )

    def save(self, snapshot: AssessmentFeatureSnapshot) -> AssessmentFeatureSnapshot:
        source_json = json.dumps(
            [item.model_dump(mode="json", by_alias=True) for item in snapshot.source_snapshots],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assessment_feature_snapshots(
                    feature_snapshot_id, session_id, feature_set_version, calculated_at,
                    source_lineage_hash, source_snapshots_json, demo_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.feature_snapshot_id,
                    snapshot.session_id,
                    snapshot.feature_set_version,
                    snapshot.calculated_at.isoformat(),
                    snapshot.source_lineage_hash,
                    source_json,
                    int(snapshot.demo_only),
                ),
            )
            connection.executemany(
                """
                INSERT INTO assessment_feature_values(
                    feature_snapshot_id, feature_code, dimension_key,
                    source_snapshot_type, value_type, status, numeric_value,
                    currency, calculation_version, demo_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot.feature_snapshot_id,
                        item.feature_code.value,
                        item.currency or "COUNT_OR_UNAVAILABLE",
                        item.source_snapshot_type.value,
                        item.value_type.value,
                        item.status.value,
                        str(item.numeric_value) if item.numeric_value is not None else None,
                        item.currency,
                        item.calculation_version,
                        int(item.demo_only),
                    )
                    for item in snapshot.feature_values
                ],
            )
        restored = self.get(snapshot.feature_snapshot_id)
        if restored is None:
            raise RuntimeError("saved feature snapshot could not be restored")
        return restored

    def get(self, feature_snapshot_id: str) -> AssessmentFeatureSnapshot | None:
        with self._connect() as connection:
            snapshot_row = connection.execute(
                """
                SELECT * FROM assessment_feature_snapshots
                WHERE feature_snapshot_id = ?
                """,
                (feature_snapshot_id,),
            ).fetchone()
            if snapshot_row is None:
                return None
            value_rows = connection.execute(
                """
                SELECT * FROM assessment_feature_values
                WHERE feature_snapshot_id = ?
                ORDER BY feature_code, dimension_key
                """,
                (feature_snapshot_id,),
            ).fetchall()
        return self._restore(snapshot_row, value_rows)

    def get_by_lineage(
        self,
        session_id: str,
        feature_set_version: str,
        source_lineage_hash: str,
    ) -> AssessmentFeatureSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT feature_snapshot_id FROM assessment_feature_snapshots
                WHERE session_id = ? AND feature_set_version = ? AND source_lineage_hash = ?
                """,
                (session_id, feature_set_version, source_lineage_hash),
            ).fetchone()
        return self.get(row["feature_snapshot_id"]) if row else None

    @staticmethod
    def _restore(
        snapshot_row: sqlite3.Row,
        value_rows: list[sqlite3.Row],
    ) -> AssessmentFeatureSnapshot:
        return AssessmentFeatureSnapshot(
            feature_snapshot_id=snapshot_row["feature_snapshot_id"],
            session_id=snapshot_row["session_id"],
            feature_set_version=snapshot_row["feature_set_version"],
            calculated_at=snapshot_row["calculated_at"],
            source_lineage_hash=snapshot_row["source_lineage_hash"],
            source_snapshots=[
                AssessmentDataSnapshotReference.model_validate(item)
                for item in json.loads(snapshot_row["source_snapshots_json"])
            ],
            feature_values=[
                NeutralFeatureValue(
                    feature_code=FeatureCode(row["feature_code"]),
                    source_snapshot_type=AssessmentSnapshotType(row["source_snapshot_type"]),
                    value_type=FeatureValueType(row["value_type"]),
                    status=FeatureValueStatus(row["status"]),
                    numeric_value=row["numeric_value"],
                    currency=row["currency"],
                    calculation_version=row["calculation_version"],
                    demo_only=bool(row["demo_only"]),
                )
                for row in value_rows
            ],
            demo_only=bool(snapshot_row["demo_only"]),
        )

    def is_ready(self) -> bool:
        if not self.database_path.exists():
            return False
        try:
            with self._connect() as connection:
                names = {
                    row["name"]
                    for row in connection.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name IN (
                            'assessment_feature_snapshots', 'assessment_feature_values'
                        )
                        """
                    ).fetchall()
                }
            return names == {"assessment_feature_snapshots", "assessment_feature_values"}
        except sqlite3.Error:
            return False
