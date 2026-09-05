import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from app.schemas.audit import SessionAuditEvent
from app.schemas.customer import (
    Borrower,
    BorrowerBusinessRole,
    Business,
    CustomerSubject,
)
from app.schemas.session import CustomerSessionState


class CustomerSessionRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create the storage structures required by the repository."""

    @abstractmethod
    def get_session(self, session_id: str) -> CustomerSessionState | None:
        """Return a customer session by its stable identifier."""

    @abstractmethod
    def get_customer_subject(self, session_id: str) -> CustomerSubject | None:
        """Return the bank-sourced customer and primary business linked to a session."""

    @abstractmethod
    def create_session(
        self,
        *,
        state: CustomerSessionState,
        audit_event: SessionAuditEvent,
    ) -> CustomerSessionState:
        """Persist a new customer session and its creation event atomically."""

    @abstractmethod
    def list_audit_events(self, session_id: str) -> list[SessionAuditEvent]:
        """Return stored audit events in creation order."""

    @abstractmethod
    def list_audit_events_page(
        self,
        session_id: str,
        *,
        before_timestamp: datetime | None,
        before_event_id: str | None,
        limit: int,
    ) -> list[SessionAuditEvent]:
        """Return one newest-first page of stored audit events."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the repository can be queried."""


class SqliteCustomerSessionRepository(CustomerSessionRepository):
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
                CREATE TABLE IF NOT EXISTS customer_sessions (
                    session_id TEXT PRIMARY KEY,
                    demo_profile_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS customer_session_audit_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_customer_session_audit_timestamp
                ON customer_session_audit_events(session_id, timestamp);

                CREATE TABLE IF NOT EXISTS borrowers (
                    borrower_id TEXT PRIMARY KEY,
                    borrower_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS businesses (
                    business_id TEXT PRIMARY KEY,
                    legal_form TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    industry_code TEXT NOT NULL,
                    industry_code_system TEXT NOT NULL,
                    industry_name TEXT NOT NULL,
                    business_started_on TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS borrower_business_roles (
                    borrower_id TEXT NOT NULL,
                    business_id TEXT NOT NULL,
                    role_type TEXT NOT NULL,
                    is_primary INTEGER NOT NULL,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    PRIMARY KEY (borrower_id, business_id),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (business_id) REFERENCES businesses(business_id)
                );

                CREATE TABLE IF NOT EXISTS customer_session_subjects (
                    session_id TEXT PRIMARY KEY,
                    borrower_id TEXT NOT NULL,
                    primary_business_id TEXT,
                    source_type TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    demo_only INTEGER NOT NULL,
                    linked_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES customer_sessions(session_id),
                    FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
                    FOREIGN KEY (primary_business_id) REFERENCES businesses(business_id)
                );

                CREATE INDEX IF NOT EXISTS idx_customer_session_subject_borrower
                ON customer_session_subjects(borrower_id);
                """
            )

    def get_session(self, session_id: str) -> CustomerSessionState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM customer_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return CustomerSessionState.model_validate_json(row["state_json"]) if row else None

    def get_customer_subject(self, session_id: str) -> CustomerSubject | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    b.borrower_id,
                    b.borrower_type,
                    b.display_name AS borrower_display_name,
                    cs.source_type,
                    cs.as_of_date,
                    cs.data_version,
                    cs.demo_only,
                    biz.business_id,
                    biz.legal_form,
                    biz.display_name AS business_display_name,
                    biz.industry_code,
                    biz.industry_code_system,
                    biz.industry_name,
                    biz.business_started_on,
                    biz.status,
                    r.role_type,
                    r.is_primary,
                    r.effective_from,
                    r.effective_to
                FROM customer_session_subjects cs
                JOIN borrowers b ON b.borrower_id = cs.borrower_id
                LEFT JOIN businesses biz ON biz.business_id = cs.primary_business_id
                LEFT JOIN borrower_business_roles r
                    ON r.borrower_id = cs.borrower_id
                    AND r.business_id = cs.primary_business_id
                WHERE cs.session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None

        business = None
        role = None
        if row["business_id"] is not None:
            business = Business(
                business_id=row["business_id"],
                legal_form=row["legal_form"],
                display_name=row["business_display_name"],
                industry_code=row["industry_code"],
                industry_code_system=row["industry_code_system"],
                industry_name=row["industry_name"],
                business_started_on=row["business_started_on"],
                status=row["status"],
            )
            role = BorrowerBusinessRole(
                borrower_id=row["borrower_id"],
                business_id=row["business_id"],
                role_type=row["role_type"],
                is_primary=bool(row["is_primary"]),
                effective_from=row["effective_from"],
                effective_to=row["effective_to"],
            )

        return CustomerSubject(
            borrower=Borrower(
                borrower_id=row["borrower_id"],
                borrower_type=row["borrower_type"],
                display_name=row["borrower_display_name"],
            ),
            primary_business=business,
            business_role=role,
            source_type=row["source_type"],
            as_of_date=row["as_of_date"],
            data_version=row["data_version"],
            demo_only=bool(row["demo_only"]),
        )

    def create_session(
        self,
        *,
        state: CustomerSessionState,
        audit_event: SessionAuditEvent,
    ) -> CustomerSessionState:
        state_json = state.model_dump_json(by_alias=True)
        event_json = audit_event.model_dump_json(by_alias=True)
        timestamp = audit_event.timestamp.isoformat()
        session = state.session
        subject = session.customer_subject
        if subject is None:
            raise ValueError("new customer sessions require customerSubject")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO borrowers(
                    borrower_id, borrower_type, display_name, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(borrower_id) DO UPDATE SET
                    borrower_type = excluded.borrower_type,
                    display_name = excluded.display_name,
                    updated_at = excluded.updated_at
                """,
                (
                    subject.borrower.borrower_id,
                    subject.borrower.borrower_type.value,
                    subject.borrower.display_name,
                    timestamp,
                    timestamp,
                ),
            )
            if subject.primary_business is not None and subject.business_role is not None:
                business = subject.primary_business
                role = subject.business_role
                connection.execute(
                    """
                    INSERT INTO businesses(
                        business_id, legal_form, display_name, industry_code,
                        industry_code_system, industry_name, business_started_on,
                        status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(business_id) DO UPDATE SET
                        legal_form = excluded.legal_form,
                        display_name = excluded.display_name,
                        industry_code = excluded.industry_code,
                        industry_code_system = excluded.industry_code_system,
                        industry_name = excluded.industry_name,
                        business_started_on = excluded.business_started_on,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        business.business_id,
                        business.legal_form.value,
                        business.display_name,
                        business.industry_code,
                        business.industry_code_system,
                        business.industry_name,
                        business.business_started_on.isoformat(),
                        business.status.value,
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO borrower_business_roles(
                        borrower_id, business_id, role_type, is_primary,
                        effective_from, effective_to
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(borrower_id, business_id) DO UPDATE SET
                        role_type = excluded.role_type,
                        is_primary = excluded.is_primary,
                        effective_from = excluded.effective_from,
                        effective_to = excluded.effective_to
                    """,
                    (
                        role.borrower_id,
                        role.business_id,
                        role.role_type.value,
                        int(role.is_primary),
                        role.effective_from.isoformat(),
                        role.effective_to.isoformat() if role.effective_to else None,
                    ),
                )
            connection.execute(
                """
                INSERT INTO customer_sessions(
                    session_id,
                    demo_profile_id,
                    state_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.demo_profile.demo_profile_id,
                    state_json,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO customer_session_subjects(
                    session_id, borrower_id, primary_business_id, source_type,
                    as_of_date, data_version, demo_only, linked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    subject.borrower.borrower_id,
                    (
                        subject.primary_business.business_id
                        if subject.primary_business is not None
                        else None
                    ),
                    subject.source_type,
                    subject.as_of_date.isoformat(),
                    subject.data_version,
                    int(subject.demo_only),
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
                    session.session_id,
                    timestamp,
                    event_json,
                ),
            )
        return state

    def list_audit_events(self, session_id: str) -> list[SessionAuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json
                FROM customer_session_audit_events
                WHERE session_id = ?
                ORDER BY timestamp, event_id
                """,
                (session_id,),
            ).fetchall()
        return [SessionAuditEvent.model_validate_json(row["event_json"]) for row in rows]

    def list_audit_events_page(
        self,
        session_id: str,
        *,
        before_timestamp: datetime | None,
        before_event_id: str | None,
        limit: int,
    ) -> list[SessionAuditEvent]:
        if (before_timestamp is None) != (before_event_id is None):
            raise ValueError("audit cursor fields must be provided together")

        parameters: list[str | int] = [session_id]
        cursor_condition = ""
        if before_timestamp is not None and before_event_id is not None:
            cursor_condition = """
                AND (timestamp < ? OR (timestamp = ? AND event_id < ?))
            """
            encoded_timestamp = before_timestamp.isoformat()
            parameters.extend([encoded_timestamp, encoded_timestamp, before_event_id])
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT event_json
                FROM customer_session_audit_events
                WHERE session_id = ?
                {cursor_condition}
                ORDER BY timestamp DESC, event_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [SessionAuditEvent.model_validate_json(row["event_json"]) for row in rows]

    def is_ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM customer_sessions LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        return True
