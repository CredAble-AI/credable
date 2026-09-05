import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.bank_data import (
    BankAccount,
    BankBalanceSnapshot,
    BankDataSnapshot,
    BankTransaction,
)


class BankDataRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create normalized storage for bank-owned account data."""

    @abstractmethod
    def save_snapshot(self, snapshot: BankDataSnapshot) -> BankDataSnapshot:
        """Persist one immutable-version Demo snapshot for a customer session."""

    @abstractmethod
    def get_snapshot(self, session_id: str) -> BankDataSnapshot | None:
        """Restore the exact bank data version linked to a session."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteBankDataRepository(BankDataRepository):
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
                CREATE TABLE IF NOT EXISTS bank_data_session_snapshots (
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

                CREATE TABLE IF NOT EXISTS bank_accounts (
                    account_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    borrower_id TEXT NOT NULL,
                    primary_business_id TEXT,
                    institution_code TEXT NOT NULL,
                    account_type TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    opened_on TEXT NOT NULL,
                    closed_on TEXT,
                    status TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, data_version),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (primary_business_id) REFERENCES businesses(business_id)
                );

                CREATE INDEX IF NOT EXISTS idx_bank_accounts_borrower
                ON bank_accounts(borrower_id, data_version);

                CREATE TABLE IF NOT EXISTS bank_account_balances (
                    account_id TEXT NOT NULL,
                    as_of_at TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    booked_balance TEXT NOT NULL,
                    available_balance TEXT,
                    currency TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    PRIMARY KEY (account_id, as_of_at, data_version),
                    FOREIGN KEY (account_id, data_version)
                        REFERENCES bank_accounts(account_id, data_version)
                );

                CREATE TABLE IF NOT EXISTS bank_transactions (
                    transaction_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    booked_at TEXT NOT NULL,
                    value_date TEXT,
                    credit_debit_indicator TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    balance_after TEXT,
                    transaction_type_code TEXT,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (transaction_id, data_version),
                    FOREIGN KEY (account_id, data_version)
                        REFERENCES bank_accounts(account_id, data_version)
                );

                CREATE INDEX IF NOT EXISTS idx_bank_transactions_account_booked
                ON bank_transactions(account_id, data_version, booked_at);
                """
            )

    def save_snapshot(self, snapshot: BankDataSnapshot) -> BankDataSnapshot:
        loaded_at = snapshot.loaded_at.isoformat()
        with self._connect() as connection:
            for account in snapshot.accounts:
                connection.execute(
                    """
                    INSERT INTO bank_accounts(
                        account_id, data_version, borrower_id, primary_business_id,
                        institution_code, account_type, currency, opened_on, closed_on,
                        status, source_type, demo_only, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, data_version) DO UPDATE SET
                        borrower_id = excluded.borrower_id,
                        primary_business_id = excluded.primary_business_id,
                        institution_code = excluded.institution_code,
                        account_type = excluded.account_type,
                        currency = excluded.currency,
                        opened_on = excluded.opened_on,
                        closed_on = excluded.closed_on,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        account.account_id,
                        snapshot.data_version,
                        account.borrower_id,
                        account.primary_business_id,
                        account.institution_code,
                        account.account_type.value,
                        account.currency,
                        account.opened_on.isoformat(),
                        account.closed_on.isoformat() if account.closed_on else None,
                        account.status.value,
                        snapshot.source_type,
                        int(snapshot.demo_only),
                        loaded_at,
                        loaded_at,
                    ),
                )

            for balance in snapshot.balances:
                connection.execute(
                    """
                    INSERT INTO bank_account_balances(
                        account_id, as_of_at, data_version, booked_balance,
                        available_balance, currency, demo_only
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, as_of_at, data_version) DO UPDATE SET
                        booked_balance = excluded.booked_balance,
                        available_balance = excluded.available_balance,
                        currency = excluded.currency
                    """,
                    (
                        balance.account_id,
                        balance.as_of_at.isoformat(),
                        snapshot.data_version,
                        str(balance.booked_balance),
                        str(balance.available_balance)
                        if balance.available_balance is not None
                        else None,
                        balance.currency,
                        int(snapshot.demo_only),
                    ),
                )

            for transaction in snapshot.transactions:
                connection.execute(
                    """
                    INSERT INTO bank_transactions(
                        transaction_id, data_version, account_id, booked_at, value_date,
                        credit_debit_indicator, amount, currency, balance_after,
                        transaction_type_code, demo_only, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(transaction_id, data_version) DO UPDATE SET
                        account_id = excluded.account_id,
                        booked_at = excluded.booked_at,
                        value_date = excluded.value_date,
                        credit_debit_indicator = excluded.credit_debit_indicator,
                        amount = excluded.amount,
                        currency = excluded.currency,
                        balance_after = excluded.balance_after,
                        transaction_type_code = excluded.transaction_type_code,
                        updated_at = excluded.updated_at
                    """,
                    (
                        transaction.transaction_id,
                        snapshot.data_version,
                        transaction.account_id,
                        transaction.booked_at.isoformat(),
                        transaction.value_date.isoformat() if transaction.value_date else None,
                        transaction.credit_debit_indicator.value,
                        str(transaction.amount),
                        transaction.currency,
                        str(transaction.balance_after)
                        if transaction.balance_after is not None
                        else None,
                        transaction.transaction_type_code,
                        int(snapshot.demo_only),
                        loaded_at,
                        loaded_at,
                    ),
                )

            connection.execute(
                """
                INSERT INTO bank_data_session_snapshots(
                    session_id, borrower_id, primary_business_id, source_type,
                    observed_at, loaded_at, data_version, demo_only
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            raise RuntimeError("bank data snapshot was not persisted")
        return stored

    def get_snapshot(self, session_id: str) -> BankDataSnapshot | None:
        with self._connect() as connection:
            snapshot_row = connection.execute(
                """
                SELECT * FROM bank_data_session_snapshots WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if snapshot_row is None:
                return None

            account_rows = connection.execute(
                """
                SELECT * FROM bank_accounts
                WHERE borrower_id = ? AND data_version = ?
                ORDER BY account_id
                """,
                (snapshot_row["borrower_id"], snapshot_row["data_version"]),
            ).fetchall()
            account_ids = [row["account_id"] for row in account_rows]
            if not account_ids:
                balance_rows = []
                transaction_rows = []
            else:
                placeholders = ",".join("?" for _ in account_ids)
                parameters = [*account_ids, snapshot_row["data_version"]]
                balance_rows = connection.execute(
                    f"""
                    SELECT * FROM bank_account_balances
                    WHERE account_id IN ({placeholders}) AND data_version = ?
                    ORDER BY as_of_at, account_id
                    """,
                    parameters,
                ).fetchall()
                transaction_rows = connection.execute(
                    f"""
                    SELECT * FROM bank_transactions
                    WHERE account_id IN ({placeholders}) AND data_version = ?
                    ORDER BY booked_at, transaction_id
                    """,
                    parameters,
                ).fetchall()

        return BankDataSnapshot(
            session_id=snapshot_row["session_id"],
            borrower_id=snapshot_row["borrower_id"],
            primary_business_id=snapshot_row["primary_business_id"],
            source_type=snapshot_row["source_type"],
            observed_at=snapshot_row["observed_at"],
            loaded_at=snapshot_row["loaded_at"],
            data_version=snapshot_row["data_version"],
            accounts=[self._to_account(row) for row in account_rows],
            balances=[self._to_balance(row) for row in balance_rows],
            transactions=[self._to_transaction(row) for row in transaction_rows],
            demo_only=bool(snapshot_row["demo_only"]),
        )

    @staticmethod
    def _to_account(row: sqlite3.Row) -> BankAccount:
        return BankAccount(
            account_id=row["account_id"],
            borrower_id=row["borrower_id"],
            primary_business_id=row["primary_business_id"],
            institution_code=row["institution_code"],
            account_type=row["account_type"],
            currency=row["currency"],
            opened_on=row["opened_on"],
            closed_on=row["closed_on"],
            status=row["status"],
        )

    @staticmethod
    def _to_balance(row: sqlite3.Row) -> BankBalanceSnapshot:
        return BankBalanceSnapshot(
            account_id=row["account_id"],
            as_of_at=row["as_of_at"],
            booked_balance=row["booked_balance"],
            available_balance=row["available_balance"],
            currency=row["currency"],
        )

    @staticmethod
    def _to_transaction(row: sqlite3.Row) -> BankTransaction:
        return BankTransaction(
            transaction_id=row["transaction_id"],
            account_id=row["account_id"],
            booked_at=row["booked_at"],
            value_date=row["value_date"],
            credit_debit_indicator=row["credit_debit_indicator"],
            amount=row["amount"],
            currency=row["currency"],
            balance_after=row["balance_after"],
            transaction_type_code=row["transaction_type_code"],
        )

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM bank_data_session_snapshots LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
