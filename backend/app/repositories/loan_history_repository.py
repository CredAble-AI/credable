import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.loan_history import (
    DelinquencyEvent,
    LoanAccount,
    LoanHistorySnapshot,
    RepaymentEvent,
    RepaymentScheduleItem,
)


class LoanHistoryRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create normalized loan servicing-history storage."""

    @abstractmethod
    def save_snapshot(self, snapshot: LoanHistorySnapshot) -> LoanHistorySnapshot:
        """Persist one immutable, versioned loan-history snapshot."""

    @abstractmethod
    def get_snapshot(self, session_id: str) -> LoanHistorySnapshot | None:
        """Restore the loan-history version fixed for a session."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteLoanHistoryRepository(LoanHistoryRepository):
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
                CREATE TABLE IF NOT EXISTS loan_history_session_snapshots (
                    session_id TEXT PRIMARY KEY,
                    borrower_id TEXT NOT NULL,
                    primary_business_id TEXT,
                    source_type TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    loaded_at TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (primary_business_id) REFERENCES businesses(business_id)
                );

                CREATE TABLE IF NOT EXISTS loan_accounts (
                    loan_account_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    borrower_id TEXT NOT NULL,
                    primary_business_id TEXT,
                    product_id TEXT,
                    originated_on TEXT NOT NULL,
                    maturity_on TEXT,
                    original_principal_amount TEXT NOT NULL,
                    outstanding_principal_amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (loan_account_id, data_version),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (primary_business_id) REFERENCES businesses(business_id)
                );

                CREATE INDEX IF NOT EXISTS idx_loan_accounts_borrower
                ON loan_accounts(borrower_id, data_version, originated_on);

                CREATE TABLE IF NOT EXISTS loan_repayment_schedules (
                    schedule_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    loan_account_id TEXT NOT NULL,
                    due_on TEXT NOT NULL,
                    scheduled_principal_amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (schedule_id, data_version),
                    FOREIGN KEY (loan_account_id, data_version)
                        REFERENCES loan_accounts(loan_account_id, data_version)
                );

                CREATE INDEX IF NOT EXISTS idx_loan_repayment_schedules_account
                ON loan_repayment_schedules(loan_account_id, data_version, due_on);

                CREATE TABLE IF NOT EXISTS loan_repayment_events (
                    repayment_event_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    loan_account_id TEXT NOT NULL,
                    schedule_id TEXT,
                    paid_at TEXT NOT NULL,
                    principal_paid_amount TEXT NOT NULL,
                    interest_paid_amount TEXT NOT NULL,
                    fee_paid_amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    source_transaction_id TEXT,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (repayment_event_id, data_version),
                    FOREIGN KEY (loan_account_id, data_version)
                        REFERENCES loan_accounts(loan_account_id, data_version),
                    FOREIGN KEY (schedule_id, data_version)
                        REFERENCES loan_repayment_schedules(schedule_id, data_version)
                );

                CREATE INDEX IF NOT EXISTS idx_loan_repayment_events_account
                ON loan_repayment_events(loan_account_id, data_version, paid_at);

                CREATE TABLE IF NOT EXISTS loan_delinquency_events (
                    delinquency_event_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    loan_account_id TEXT NOT NULL,
                    schedule_id TEXT,
                    started_at TEXT NOT NULL,
                    cured_at TEXT,
                    max_days_past_due INTEGER NOT NULL,
                    overdue_principal_amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (delinquency_event_id, data_version),
                    FOREIGN KEY (loan_account_id, data_version)
                        REFERENCES loan_accounts(loan_account_id, data_version),
                    FOREIGN KEY (schedule_id, data_version)
                        REFERENCES loan_repayment_schedules(schedule_id, data_version)
                );

                CREATE INDEX IF NOT EXISTS idx_loan_delinquency_events_account
                ON loan_delinquency_events(loan_account_id, data_version, started_at);
                """
            )

    def save_snapshot(self, snapshot: LoanHistorySnapshot) -> LoanHistorySnapshot:
        loaded_at = snapshot.loaded_at.isoformat()
        with self._connect() as connection:
            for account in snapshot.loan_accounts:
                connection.execute(
                    """
                    INSERT INTO loan_accounts(
                        loan_account_id, data_version, borrower_id, primary_business_id,
                        product_id, originated_on, maturity_on, original_principal_amount,
                        outstanding_principal_amount, currency, status, demo_only, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(loan_account_id, data_version) DO NOTHING
                    """,
                    (
                        account.loan_account_id,
                        snapshot.data_version,
                        account.borrower_id,
                        account.primary_business_id,
                        account.product_id,
                        account.originated_on.isoformat(),
                        account.maturity_on.isoformat() if account.maturity_on else None,
                        str(account.original_principal_amount),
                        str(account.outstanding_principal_amount),
                        account.currency,
                        account.status.value,
                        int(snapshot.demo_only),
                        loaded_at,
                    ),
                )

            for schedule in snapshot.repayment_schedules:
                connection.execute(
                    """
                    INSERT INTO loan_repayment_schedules(
                        schedule_id, data_version, loan_account_id, due_on,
                        scheduled_principal_amount, currency, status, demo_only, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(schedule_id, data_version) DO NOTHING
                    """,
                    (
                        schedule.schedule_id,
                        snapshot.data_version,
                        schedule.loan_account_id,
                        schedule.due_on.isoformat(),
                        str(schedule.scheduled_principal_amount),
                        schedule.currency,
                        schedule.status.value,
                        int(snapshot.demo_only),
                        loaded_at,
                    ),
                )

            for repayment in snapshot.repayment_events:
                connection.execute(
                    """
                    INSERT INTO loan_repayment_events(
                        repayment_event_id, data_version, loan_account_id, schedule_id,
                        paid_at, principal_paid_amount, interest_paid_amount, fee_paid_amount,
                        currency, source_transaction_id, demo_only, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repayment_event_id, data_version) DO NOTHING
                    """,
                    (
                        repayment.repayment_event_id,
                        snapshot.data_version,
                        repayment.loan_account_id,
                        repayment.schedule_id,
                        repayment.paid_at.isoformat(),
                        str(repayment.principal_paid_amount),
                        str(repayment.interest_paid_amount),
                        str(repayment.fee_paid_amount),
                        repayment.currency,
                        repayment.source_transaction_id,
                        int(snapshot.demo_only),
                        loaded_at,
                    ),
                )

            for delinquency in snapshot.delinquency_events:
                connection.execute(
                    """
                    INSERT INTO loan_delinquency_events(
                        delinquency_event_id, data_version, loan_account_id, schedule_id,
                        started_at, cured_at, max_days_past_due, overdue_principal_amount,
                        currency, status, demo_only, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(delinquency_event_id, data_version) DO NOTHING
                    """,
                    (
                        delinquency.delinquency_event_id,
                        snapshot.data_version,
                        delinquency.loan_account_id,
                        delinquency.schedule_id,
                        delinquency.started_at.isoformat(),
                        delinquency.cured_at.isoformat() if delinquency.cured_at else None,
                        delinquency.max_days_past_due,
                        str(delinquency.overdue_principal_amount),
                        delinquency.currency,
                        delinquency.status.value,
                        int(snapshot.demo_only),
                        loaded_at,
                    ),
                )

            connection.execute(
                """
                INSERT INTO loan_history_session_snapshots(
                    session_id, borrower_id, primary_business_id, source_type,
                    observed_at, loaded_at, data_version, demo_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (
                    snapshot.session_id,
                    snapshot.borrower_id,
                    snapshot.primary_business_id,
                    snapshot.source_type,
                    snapshot.observed_at.isoformat(),
                    loaded_at,
                    snapshot.data_version,
                    int(snapshot.demo_only),
                ),
            )
        stored = self.get_snapshot(snapshot.session_id)
        if stored is None:
            raise RuntimeError("loan history snapshot was not persisted")
        return stored

    def get_snapshot(self, session_id: str) -> LoanHistorySnapshot | None:
        with self._connect() as connection:
            snapshot = connection.execute(
                "SELECT * FROM loan_history_session_snapshots WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if snapshot is None:
                return None

            key = (snapshot["borrower_id"], snapshot["data_version"])
            account_rows = connection.execute(
                """
                SELECT * FROM loan_accounts
                WHERE borrower_id = ? AND data_version = ?
                ORDER BY originated_on, loan_account_id
                """,
                key,
            ).fetchall()
            account_ids = [row["loan_account_id"] for row in account_rows]
            schedule_rows = self._rows_for_accounts(
                connection,
                table="loan_repayment_schedules",
                account_ids=account_ids,
                data_version=snapshot["data_version"],
                order_by="due_on, schedule_id",
            )
            repayment_rows = self._rows_for_accounts(
                connection,
                table="loan_repayment_events",
                account_ids=account_ids,
                data_version=snapshot["data_version"],
                order_by="paid_at, repayment_event_id",
            )
            delinquency_rows = self._rows_for_accounts(
                connection,
                table="loan_delinquency_events",
                account_ids=account_ids,
                data_version=snapshot["data_version"],
                order_by="started_at, delinquency_event_id",
            )

        return LoanHistorySnapshot(
            session_id=snapshot["session_id"],
            borrower_id=snapshot["borrower_id"],
            primary_business_id=snapshot["primary_business_id"],
            source_type=snapshot["source_type"],
            observed_at=snapshot["observed_at"],
            loaded_at=snapshot["loaded_at"],
            data_version=snapshot["data_version"],
            loan_accounts=[self._to_account(row) for row in account_rows],
            repayment_schedules=[self._to_schedule(row) for row in schedule_rows],
            repayment_events=[self._to_repayment(row) for row in repayment_rows],
            delinquency_events=[self._to_delinquency(row) for row in delinquency_rows],
            demo_only=bool(snapshot["demo_only"]),
        )

    @staticmethod
    def _rows_for_accounts(
        connection: sqlite3.Connection,
        *,
        table: str,
        account_ids: list[str],
        data_version: str,
        order_by: str,
    ) -> list[sqlite3.Row]:
        if not account_ids:
            return []
        placeholders = ",".join("?" for _ in account_ids)
        return connection.execute(
            f"""
            SELECT * FROM {table}
            WHERE loan_account_id IN ({placeholders}) AND data_version = ?
            ORDER BY {order_by}
            """,
            [*account_ids, data_version],
        ).fetchall()

    @staticmethod
    def _to_account(row: sqlite3.Row) -> LoanAccount:
        return LoanAccount(
            loan_account_id=row["loan_account_id"],
            borrower_id=row["borrower_id"],
            primary_business_id=row["primary_business_id"],
            product_id=row["product_id"],
            originated_on=row["originated_on"],
            maturity_on=row["maturity_on"],
            original_principal_amount=row["original_principal_amount"],
            outstanding_principal_amount=row["outstanding_principal_amount"],
            currency=row["currency"],
            status=row["status"],
        )

    @staticmethod
    def _to_schedule(row: sqlite3.Row) -> RepaymentScheduleItem:
        return RepaymentScheduleItem(
            schedule_id=row["schedule_id"],
            loan_account_id=row["loan_account_id"],
            due_on=row["due_on"],
            scheduled_principal_amount=row["scheduled_principal_amount"],
            currency=row["currency"],
            status=row["status"],
        )

    @staticmethod
    def _to_repayment(row: sqlite3.Row) -> RepaymentEvent:
        return RepaymentEvent(
            repayment_event_id=row["repayment_event_id"],
            loan_account_id=row["loan_account_id"],
            schedule_id=row["schedule_id"],
            paid_at=row["paid_at"],
            principal_paid_amount=row["principal_paid_amount"],
            interest_paid_amount=row["interest_paid_amount"],
            fee_paid_amount=row["fee_paid_amount"],
            currency=row["currency"],
            source_transaction_id=row["source_transaction_id"],
        )

    @staticmethod
    def _to_delinquency(row: sqlite3.Row) -> DelinquencyEvent:
        return DelinquencyEvent(
            delinquency_event_id=row["delinquency_event_id"],
            loan_account_id=row["loan_account_id"],
            schedule_id=row["schedule_id"],
            started_at=row["started_at"],
            cured_at=row["cured_at"],
            max_days_past_due=row["max_days_past_due"],
            overdue_principal_amount=row["overdue_principal_amount"],
            currency=row["currency"],
            status=row["status"],
        )

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    "SELECT 1 FROM loan_history_session_snapshots LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            return False
        return True
