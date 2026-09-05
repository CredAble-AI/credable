import sqlite3

from fastapi.testclient import TestClient

from app.repositories.loan_history_repository import SqliteLoanHistoryRepository
from app.schemas.loan_history import DelinquencyStatus, LoanAccountStatus
from app.services.loan_history_service import LoanHistoryService


def create_session(client: TestClient, demo_profile_id: str) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def test_existing_loan_preserves_servicing_and_cured_delinquency_facts(
    client: TestClient,
    loan_history_service: LoanHistoryService,
    loan_history_repository: SqliteLoanHistoryRepository,
) -> None:
    session_id = create_session(client, "small-business")

    snapshot = loan_history_service.get_or_materialize_snapshot(session_id)

    assert snapshot.source_type == "BANK_INTERNAL"
    assert snapshot.data_version == "synthetic-bank-data-v1"
    assert len(snapshot.loan_accounts) == 1
    account = snapshot.loan_accounts[0]
    assert account.status == LoanAccountStatus.ACTIVE
    assert account.original_principal_amount == 14_000_000
    assert account.outstanding_principal_amount == 12_000_000

    assert len(snapshot.repayment_schedules) == 2
    assert len(snapshot.repayment_events) == 2
    assert sum(event.principal_paid_amount for event in snapshot.repayment_events) == 2_000_000
    assert len(snapshot.delinquency_events) == 1
    delinquency = snapshot.delinquency_events[0]
    assert delinquency.status == DelinquencyStatus.CURED
    assert delinquency.max_days_past_due == 1
    assert delinquency.cured_at is not None

    reopened = SqliteLoanHistoryRepository(loan_history_repository.database_path)
    reopened.initialize()
    assert reopened.get_snapshot(session_id) == snapshot
    assert loan_history_service.get_or_materialize_snapshot(session_id) == snapshot


def test_customer_without_prior_loan_keeps_explicit_empty_history(
    client: TestClient,
    loan_history_service: LoanHistoryService,
    loan_history_repository: SqliteLoanHistoryRepository,
) -> None:
    session_id = create_session(client, "startup")

    snapshot = loan_history_service.get_or_materialize_snapshot(session_id)

    assert snapshot.loan_accounts == []
    assert snapshot.repayment_schedules == []
    assert snapshot.repayment_events == []
    assert snapshot.delinquency_events == []
    with sqlite3.connect(loan_history_repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM loan_accounts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM loan_repayment_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM loan_delinquency_events").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM loan_history_session_snapshots").fetchone()[0]
            == 1
        )


def test_fixture_stores_facts_without_inventing_risk_or_product_terms(
    loan_history_service: LoanHistoryService,
) -> None:
    fixture_text = loan_history_service.catalog.catalog_path.read_text(encoding="utf-8")

    excluded_fields = {
        "riskGrade",
        "probabilityOfDefault",
        "approvalThreshold",
        "approvedAmount",
        "interestRate",
        "creditLimit",
    }
    assert all(field not in fixture_text for field in excluded_fields)
