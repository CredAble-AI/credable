import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.credit_exposure import (
    CreditExposureSnapshot,
    ExternalCreditDelinquency,
    ExternalCreditExposure,
    ExternalCreditGuarantee,
)


class CreditExposureRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create normalized external credit-information storage."""

    @abstractmethod
    def save_snapshot(self, snapshot: CreditExposureSnapshot) -> CreditExposureSnapshot:
        """Persist one immutable, versioned credit-information snapshot."""

    @abstractmethod
    def get_snapshot(self, session_id: str) -> CreditExposureSnapshot | None:
        """Restore the credit-information version fixed for a session."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteCreditExposureRepository(CreditExposureRepository):
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
                CREATE TABLE IF NOT EXISTS credit_exposure_session_snapshots (
                    session_id TEXT PRIMARY KEY,
                    borrower_id TEXT NOT NULL,
                    primary_business_id TEXT,
                    source_type TEXT NOT NULL,
                    provider_code TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    reported_at TEXT NOT NULL,
                    loaded_at TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (primary_business_id) REFERENCES businesses(business_id)
                );

                CREATE TABLE IF NOT EXISTS external_credit_exposures (
                    exposure_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    borrower_id TEXT NOT NULL,
                    primary_business_id TEXT,
                    reporting_institution_code TEXT NOT NULL,
                    institution_sector TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    opened_on TEXT NOT NULL,
                    maturity_on TEXT,
                    original_principal_amount TEXT,
                    outstanding_balance TEXT NOT NULL,
                    annual_interest_rate_percent TEXT,
                    currency TEXT NOT NULL,
                    security_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (exposure_id, data_version),
                    UNIQUE (source_record_id, data_version),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (primary_business_id) REFERENCES businesses(business_id)
                );

                CREATE INDEX IF NOT EXISTS idx_external_credit_exposures_borrower
                ON external_credit_exposures(borrower_id, data_version, opened_on);

                CREATE TABLE IF NOT EXISTS external_credit_delinquencies (
                    delinquency_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    exposure_id TEXT NOT NULL,
                    started_on TEXT NOT NULL,
                    cured_on TEXT,
                    max_days_past_due INTEGER NOT NULL,
                    overdue_principal_amount TEXT NOT NULL,
                    overdue_interest_amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason_code TEXT,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (delinquency_id, data_version),
                    FOREIGN KEY (exposure_id, data_version)
                        REFERENCES external_credit_exposures(exposure_id, data_version)
                );

                CREATE INDEX IF NOT EXISTS idx_external_credit_delinquencies_exposure
                ON external_credit_delinquencies(exposure_id, data_version, started_on);

                CREATE TABLE IF NOT EXISTS external_credit_guarantees (
                    guarantee_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    exposure_id TEXT NOT NULL,
                    guarantor_institution_code TEXT NOT NULL,
                    guarantee_type_code TEXT NOT NULL,
                    started_on TEXT NOT NULL,
                    ended_on TEXT,
                    guaranteed_amount TEXT NOT NULL,
                    outstanding_guaranteed_amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (guarantee_id, data_version),
                    FOREIGN KEY (exposure_id, data_version)
                        REFERENCES external_credit_exposures(exposure_id, data_version)
                );

                CREATE INDEX IF NOT EXISTS idx_external_credit_guarantees_exposure
                ON external_credit_guarantees(exposure_id, data_version, started_on);
                """
            )

    def save_snapshot(self, snapshot: CreditExposureSnapshot) -> CreditExposureSnapshot:
        loaded_at = snapshot.loaded_at.isoformat()
        with self._connect() as connection:
            for exposure in snapshot.exposures:
                connection.execute(
                    """
                    INSERT INTO external_credit_exposures(
                        exposure_id, data_version, source_record_id, borrower_id,
                        primary_business_id, reporting_institution_code, institution_sector,
                        product_type, opened_on, maturity_on, original_principal_amount,
                        outstanding_balance, annual_interest_rate_percent, currency,
                        security_type, status, demo_only, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(exposure_id, data_version) DO NOTHING
                    """,
                    (
                        exposure.exposure_id,
                        snapshot.data_version,
                        exposure.source_record_id,
                        exposure.borrower_id,
                        exposure.primary_business_id,
                        exposure.reporting_institution_code,
                        exposure.institution_sector.value,
                        exposure.product_type.value,
                        exposure.opened_on.isoformat(),
                        exposure.maturity_on.isoformat() if exposure.maturity_on else None,
                        (
                            str(exposure.original_principal_amount)
                            if exposure.original_principal_amount is not None
                            else None
                        ),
                        str(exposure.outstanding_balance),
                        (
                            str(exposure.annual_interest_rate_percent)
                            if exposure.annual_interest_rate_percent is not None
                            else None
                        ),
                        exposure.currency,
                        exposure.security_type.value,
                        exposure.status.value,
                        int(snapshot.demo_only),
                        loaded_at,
                    ),
                )

            for delinquency in snapshot.delinquencies:
                connection.execute(
                    """
                    INSERT INTO external_credit_delinquencies(
                        delinquency_id, data_version, exposure_id, started_on, cured_on,
                        max_days_past_due, overdue_principal_amount, overdue_interest_amount,
                        currency, status, reason_code, demo_only, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(delinquency_id, data_version) DO NOTHING
                    """,
                    (
                        delinquency.delinquency_id,
                        snapshot.data_version,
                        delinquency.exposure_id,
                        delinquency.started_on.isoformat(),
                        delinquency.cured_on.isoformat() if delinquency.cured_on else None,
                        delinquency.max_days_past_due,
                        str(delinquency.overdue_principal_amount),
                        str(delinquency.overdue_interest_amount),
                        delinquency.currency,
                        delinquency.status.value,
                        delinquency.reason_code,
                        int(snapshot.demo_only),
                        loaded_at,
                    ),
                )

            for guarantee in snapshot.guarantees:
                connection.execute(
                    """
                    INSERT INTO external_credit_guarantees(
                        guarantee_id, data_version, exposure_id, guarantor_institution_code,
                        guarantee_type_code, started_on, ended_on, guaranteed_amount,
                        outstanding_guaranteed_amount, currency, status, demo_only, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guarantee_id, data_version) DO NOTHING
                    """,
                    (
                        guarantee.guarantee_id,
                        snapshot.data_version,
                        guarantee.exposure_id,
                        guarantee.guarantor_institution_code,
                        guarantee.guarantee_type_code,
                        guarantee.started_on.isoformat(),
                        guarantee.ended_on.isoformat() if guarantee.ended_on else None,
                        str(guarantee.guaranteed_amount),
                        str(guarantee.outstanding_guaranteed_amount),
                        guarantee.currency,
                        guarantee.status.value,
                        int(snapshot.demo_only),
                        loaded_at,
                    ),
                )

            connection.execute(
                """
                INSERT INTO credit_exposure_session_snapshots(
                    session_id, borrower_id, primary_business_id, source_type,
                    provider_code, report_id, reported_at, loaded_at, data_version, demo_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (
                    snapshot.session_id,
                    snapshot.borrower_id,
                    snapshot.primary_business_id,
                    snapshot.source_type,
                    snapshot.provider_code,
                    snapshot.report_id,
                    snapshot.reported_at.isoformat(),
                    loaded_at,
                    snapshot.data_version,
                    int(snapshot.demo_only),
                ),
            )
        stored = self.get_snapshot(snapshot.session_id)
        if stored is None:
            raise RuntimeError("credit exposure snapshot was not persisted")
        return stored

    def get_snapshot(self, session_id: str) -> CreditExposureSnapshot | None:
        with self._connect() as connection:
            snapshot = connection.execute(
                "SELECT * FROM credit_exposure_session_snapshots WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if snapshot is None:
                return None

            key = (snapshot["borrower_id"], snapshot["data_version"])
            exposure_rows = connection.execute(
                """
                SELECT * FROM external_credit_exposures
                WHERE borrower_id = ? AND data_version = ?
                ORDER BY opened_on, exposure_id
                """,
                key,
            ).fetchall()
            exposure_ids = [row["exposure_id"] for row in exposure_rows]
            delinquency_rows = self._rows_for_exposures(
                connection,
                table="external_credit_delinquencies",
                exposure_ids=exposure_ids,
                data_version=snapshot["data_version"],
                order_by="started_on, delinquency_id",
            )
            guarantee_rows = self._rows_for_exposures(
                connection,
                table="external_credit_guarantees",
                exposure_ids=exposure_ids,
                data_version=snapshot["data_version"],
                order_by="started_on, guarantee_id",
            )

        return CreditExposureSnapshot(
            session_id=snapshot["session_id"],
            borrower_id=snapshot["borrower_id"],
            primary_business_id=snapshot["primary_business_id"],
            source_type=snapshot["source_type"],
            provider_code=snapshot["provider_code"],
            report_id=snapshot["report_id"],
            reported_at=snapshot["reported_at"],
            loaded_at=snapshot["loaded_at"],
            data_version=snapshot["data_version"],
            exposures=[self._to_exposure(row) for row in exposure_rows],
            delinquencies=[self._to_delinquency(row) for row in delinquency_rows],
            guarantees=[self._to_guarantee(row) for row in guarantee_rows],
            demo_only=bool(snapshot["demo_only"]),
        )

    @staticmethod
    def _rows_for_exposures(
        connection: sqlite3.Connection,
        *,
        table: str,
        exposure_ids: list[str],
        data_version: str,
        order_by: str,
    ) -> list[sqlite3.Row]:
        if not exposure_ids:
            return []
        placeholders = ",".join("?" for _ in exposure_ids)
        return connection.execute(
            f"""
            SELECT * FROM {table}
            WHERE exposure_id IN ({placeholders}) AND data_version = ?
            ORDER BY {order_by}
            """,
            [*exposure_ids, data_version],
        ).fetchall()

    @staticmethod
    def _to_exposure(row: sqlite3.Row) -> ExternalCreditExposure:
        return ExternalCreditExposure(
            exposure_id=row["exposure_id"],
            source_record_id=row["source_record_id"],
            borrower_id=row["borrower_id"],
            primary_business_id=row["primary_business_id"],
            reporting_institution_code=row["reporting_institution_code"],
            institution_sector=row["institution_sector"],
            product_type=row["product_type"],
            opened_on=row["opened_on"],
            maturity_on=row["maturity_on"],
            original_principal_amount=row["original_principal_amount"],
            outstanding_balance=row["outstanding_balance"],
            annual_interest_rate_percent=row["annual_interest_rate_percent"],
            currency=row["currency"],
            security_type=row["security_type"],
            status=row["status"],
        )

    @staticmethod
    def _to_delinquency(row: sqlite3.Row) -> ExternalCreditDelinquency:
        return ExternalCreditDelinquency(
            delinquency_id=row["delinquency_id"],
            exposure_id=row["exposure_id"],
            started_on=row["started_on"],
            cured_on=row["cured_on"],
            max_days_past_due=row["max_days_past_due"],
            overdue_principal_amount=row["overdue_principal_amount"],
            overdue_interest_amount=row["overdue_interest_amount"],
            currency=row["currency"],
            status=row["status"],
            reason_code=row["reason_code"],
        )

    @staticmethod
    def _to_guarantee(row: sqlite3.Row) -> ExternalCreditGuarantee:
        return ExternalCreditGuarantee(
            guarantee_id=row["guarantee_id"],
            exposure_id=row["exposure_id"],
            guarantor_institution_code=row["guarantor_institution_code"],
            guarantee_type_code=row["guarantee_type_code"],
            started_on=row["started_on"],
            ended_on=row["ended_on"],
            guaranteed_amount=row["guaranteed_amount"],
            outstanding_guaranteed_amount=row["outstanding_guaranteed_amount"],
            currency=row["currency"],
            status=row["status"],
        )

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    "SELECT 1 FROM credit_exposure_session_snapshots LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            return False
        return True
