import sqlite3
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path

from app.schemas.credit_history import (
    BankCreditAssessment,
    CreditHistorySnapshot,
    LoanApplication,
    LoanDecision,
)


class CreditHistoryRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create normalized application, decision, and assessment storage."""

    @abstractmethod
    def save_snapshot(self, snapshot: CreditHistorySnapshot) -> CreditHistorySnapshot:
        """Persist one versioned bank credit-history snapshot."""

    @abstractmethod
    def get_snapshot(self, session_id: str) -> CreditHistorySnapshot | None:
        """Restore the credit-history version fixed for a session."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteCreditHistoryRepository(CreditHistoryRepository):
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
                CREATE TABLE IF NOT EXISTS credit_history_session_snapshots (
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

                CREATE TABLE IF NOT EXISTS loan_applications (
                    application_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    borrower_id TEXT NOT NULL,
                    primary_business_id TEXT,
                    product_id TEXT,
                    submitted_at TEXT NOT NULL,
                    requested_amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    requested_term_months INTEGER,
                    status TEXT NOT NULL,
                    resolved_at TEXT,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (application_id, data_version),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (primary_business_id) REFERENCES businesses(business_id)
                );

                CREATE INDEX IF NOT EXISTS idx_loan_applications_borrower
                ON loan_applications(borrower_id, data_version, submitted_at);

                CREATE TABLE IF NOT EXISTS loan_decisions (
                    decision_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    application_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (decision_id, data_version),
                    FOREIGN KEY (application_id, data_version)
                        REFERENCES loan_applications(application_id, data_version)
                );

                CREATE TABLE IF NOT EXISTS loan_decision_reasons (
                    decision_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    reason_order INTEGER NOT NULL,
                    reason_code TEXT NOT NULL,
                    PRIMARY KEY (decision_id, data_version, reason_order),
                    FOREIGN KEY (decision_id, data_version)
                        REFERENCES loan_decisions(decision_id, data_version)
                );

                CREATE TABLE IF NOT EXISTS bank_credit_assessments (
                    credit_assessment_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    borrower_id TEXT NOT NULL,
                    primary_business_id TEXT,
                    application_id TEXT,
                    assessment_type TEXT NOT NULL,
                    assessed_at TEXT NOT NULL,
                    feature_cutoff_at TEXT NOT NULL,
                    grade_code TEXT NOT NULL,
                    grade_scale_version TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    feature_set_version TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (credit_assessment_id, data_version),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (primary_business_id) REFERENCES businesses(business_id),
                    FOREIGN KEY (application_id, data_version)
                        REFERENCES loan_applications(application_id, data_version)
                );

                CREATE INDEX IF NOT EXISTS idx_bank_credit_assessments_borrower
                ON bank_credit_assessments(borrower_id, data_version, assessed_at);

                CREATE TABLE IF NOT EXISTS bank_credit_assessment_reasons (
                    credit_assessment_id TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    reason_order INTEGER NOT NULL,
                    reason_code TEXT NOT NULL,
                    PRIMARY KEY (credit_assessment_id, data_version, reason_order),
                    FOREIGN KEY (credit_assessment_id, data_version)
                        REFERENCES bank_credit_assessments(credit_assessment_id, data_version)
                );
                """
            )

    def save_snapshot(self, snapshot: CreditHistorySnapshot) -> CreditHistorySnapshot:
        loaded_at = snapshot.loaded_at.isoformat()
        with self._connect() as connection:
            for application in snapshot.applications:
                connection.execute(
                    """
                    INSERT INTO loan_applications(
                        application_id, data_version, borrower_id, primary_business_id,
                        product_id, submitted_at, requested_amount, currency,
                        requested_term_months, status, resolved_at, demo_only,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(application_id, data_version) DO NOTHING
                    """,
                    (
                        application.application_id,
                        snapshot.data_version,
                        application.borrower_id,
                        application.primary_business_id,
                        application.product_id,
                        application.submitted_at.isoformat(),
                        str(application.requested_amount),
                        application.currency,
                        application.requested_term_months,
                        application.status.value,
                        application.resolved_at.isoformat() if application.resolved_at else None,
                        int(snapshot.demo_only),
                        loaded_at,
                        loaded_at,
                    ),
                )

            for decision in snapshot.decisions:
                connection.execute(
                    """
                    INSERT INTO loan_decisions(
                        decision_id, data_version, application_id, outcome, decided_at,
                        policy_version, demo_only, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(decision_id, data_version) DO NOTHING
                    """,
                    (
                        decision.decision_id,
                        snapshot.data_version,
                        decision.application_id,
                        decision.outcome.value,
                        decision.decided_at.isoformat(),
                        decision.policy_version,
                        int(snapshot.demo_only),
                        loaded_at,
                        loaded_at,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO loan_decision_reasons(
                        decision_id, data_version, reason_order, reason_code
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(decision_id, data_version, reason_order) DO NOTHING
                    """,
                    [
                        (decision.decision_id, snapshot.data_version, index, reason)
                        for index, reason in enumerate(decision.reason_codes)
                    ],
                )

            for assessment in snapshot.credit_assessments:
                connection.execute(
                    """
                    INSERT INTO bank_credit_assessments(
                        credit_assessment_id, data_version, borrower_id,
                        primary_business_id, application_id, assessment_type,
                        assessed_at, feature_cutoff_at, grade_code, grade_scale_version,
                        model_version, feature_set_version, policy_version, demo_only,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(credit_assessment_id, data_version) DO NOTHING
                    """,
                    (
                        assessment.credit_assessment_id,
                        snapshot.data_version,
                        assessment.borrower_id,
                        assessment.primary_business_id,
                        assessment.application_id,
                        assessment.assessment_type.value,
                        assessment.assessed_at.isoformat(),
                        assessment.feature_cutoff_at.isoformat(),
                        assessment.grade_code,
                        assessment.grade_scale_version,
                        assessment.model_version,
                        assessment.feature_set_version,
                        assessment.policy_version,
                        int(snapshot.demo_only),
                        loaded_at,
                        loaded_at,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO bank_credit_assessment_reasons(
                        credit_assessment_id, data_version, reason_order, reason_code
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(credit_assessment_id, data_version, reason_order) DO NOTHING
                    """,
                    [
                        (assessment.credit_assessment_id, snapshot.data_version, index, reason)
                        for index, reason in enumerate(assessment.reason_codes)
                    ],
                )

            connection.execute(
                """
                INSERT INTO credit_history_session_snapshots(
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
            raise RuntimeError("credit history snapshot was not persisted")
        return stored

    def get_snapshot(self, session_id: str) -> CreditHistorySnapshot | None:
        with self._connect() as connection:
            snapshot = connection.execute(
                "SELECT * FROM credit_history_session_snapshots WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if snapshot is None:
                return None
            key = (snapshot["borrower_id"], snapshot["data_version"])
            application_rows = connection.execute(
                """
                SELECT * FROM loan_applications
                WHERE borrower_id = ? AND data_version = ? ORDER BY submitted_at, application_id
                """,
                key,
            ).fetchall()
            application_ids = [row["application_id"] for row in application_rows]
            decision_rows = self._rows_for_ids(
                connection,
                table="loan_decisions",
                id_column="application_id",
                ids=application_ids,
                data_version=snapshot["data_version"],
                order_by="decided_at, decision_id",
            )
            assessment_rows = connection.execute(
                """
                SELECT * FROM bank_credit_assessments
                WHERE borrower_id = ? AND data_version = ?
                ORDER BY assessed_at, credit_assessment_id
                """,
                key,
            ).fetchall()
            decision_reasons = self._reason_codes(
                connection,
                table="loan_decision_reasons",
                id_column="decision_id",
                ids=[row["decision_id"] for row in decision_rows],
                data_version=snapshot["data_version"],
            )
            assessment_reasons = self._reason_codes(
                connection,
                table="bank_credit_assessment_reasons",
                id_column="credit_assessment_id",
                ids=[row["credit_assessment_id"] for row in assessment_rows],
                data_version=snapshot["data_version"],
            )

        return CreditHistorySnapshot(
            session_id=snapshot["session_id"],
            borrower_id=snapshot["borrower_id"],
            primary_business_id=snapshot["primary_business_id"],
            source_type=snapshot["source_type"],
            observed_at=snapshot["observed_at"],
            loaded_at=snapshot["loaded_at"],
            data_version=snapshot["data_version"],
            applications=[self._to_application(row) for row in application_rows],
            decisions=[
                self._to_decision(row, decision_reasons[row["decision_id"]])
                for row in decision_rows
            ],
            credit_assessments=[
                self._to_assessment(row, assessment_reasons[row["credit_assessment_id"]])
                for row in assessment_rows
            ],
            demo_only=bool(snapshot["demo_only"]),
        )

    @staticmethod
    def _rows_for_ids(
        connection: sqlite3.Connection,
        *,
        table: str,
        id_column: str,
        ids: list[str],
        data_version: str,
        order_by: str,
    ) -> list[sqlite3.Row]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        return connection.execute(
            f"""
            SELECT * FROM {table}
            WHERE {id_column} IN ({placeholders}) AND data_version = ?
            ORDER BY {order_by}
            """,
            [*ids, data_version],
        ).fetchall()

    @classmethod
    def _reason_codes(
        cls,
        connection: sqlite3.Connection,
        *,
        table: str,
        id_column: str,
        ids: list[str],
        data_version: str,
    ) -> defaultdict[str, list[str]]:
        rows = cls._rows_for_ids(
            connection,
            table=table,
            id_column=id_column,
            ids=ids,
            data_version=data_version,
            order_by=f"{id_column}, reason_order",
        )
        reasons: defaultdict[str, list[str]] = defaultdict(list)
        for row in rows:
            reasons[row[id_column]].append(row["reason_code"])
        return reasons

    @staticmethod
    def _to_application(row: sqlite3.Row) -> LoanApplication:
        return LoanApplication(
            application_id=row["application_id"],
            borrower_id=row["borrower_id"],
            primary_business_id=row["primary_business_id"],
            product_id=row["product_id"],
            submitted_at=row["submitted_at"],
            requested_amount=row["requested_amount"],
            currency=row["currency"],
            requested_term_months=row["requested_term_months"],
            status=row["status"],
            resolved_at=row["resolved_at"],
        )

    @staticmethod
    def _to_decision(row: sqlite3.Row, reason_codes: list[str]) -> LoanDecision:
        return LoanDecision(
            decision_id=row["decision_id"],
            application_id=row["application_id"],
            outcome=row["outcome"],
            decided_at=row["decided_at"],
            reason_codes=reason_codes,
            policy_version=row["policy_version"],
        )

    @staticmethod
    def _to_assessment(row: sqlite3.Row, reason_codes: list[str]) -> BankCreditAssessment:
        return BankCreditAssessment(
            credit_assessment_id=row["credit_assessment_id"],
            borrower_id=row["borrower_id"],
            primary_business_id=row["primary_business_id"],
            application_id=row["application_id"],
            assessment_type=row["assessment_type"],
            assessed_at=row["assessed_at"],
            feature_cutoff_at=row["feature_cutoff_at"],
            grade_code=row["grade_code"],
            grade_scale_version=row["grade_scale_version"],
            reason_codes=reason_codes,
            model_version=row["model_version"],
            feature_set_version=row["feature_set_version"],
            policy_version=row["policy_version"],
        )

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    "SELECT 1 FROM credit_history_session_snapshots LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            return False
        return True
