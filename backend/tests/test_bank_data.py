import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from app.repositories.bank_data_repository import SqliteBankDataRepository
from app.schemas.bank_data import BankAccountType, CreditDebitIndicator
from app.services.bank_data_service import BankDataService


def create_session(client: TestClient, demo_profile_id: str) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def test_materializes_normalized_bank_snapshot_for_customer_session(
    client: TestClient,
    bank_data_service: BankDataService,
    bank_data_repository: SqliteBankDataRepository,
) -> None:
    session_id = create_session(client, "small-business")

    snapshot = bank_data_service.get_or_materialize_snapshot(session_id)

    assert snapshot.session_id == session_id
    assert snapshot.borrower_id == "bor_demo_001"
    assert snapshot.primary_business_id == "biz_demo_001"
    assert snapshot.source_type == "BANK_INTERNAL"
    assert snapshot.data_version == "synthetic-bank-data-v1"
    assert snapshot.observed_at.isoformat() == "2026-08-31T23:59:59+09:00"
    assert len(snapshot.accounts) == 1
    assert len(snapshot.balances) == 1
    assert len(snapshot.transactions) == 12
    assert snapshot.accounts[0].account_type == BankAccountType.DEMAND_DEPOSIT
    assert snapshot.accounts[0].institution_code == "DEMO_BANK"
    assert snapshot.balances[0].booked_balance == 7_840_000
    assert {item.credit_debit_indicator for item in snapshot.transactions} == {
        CreditDebitIndicator.CREDIT,
        CreditDebitIndicator.DEBIT,
    }
    assert snapshot.transactions[0].booked_at.date() == date(2026, 3, 5)
    assert snapshot.transactions[-1].booked_at.date() == date(2026, 8, 28)
    assert all(item.booked_at <= snapshot.observed_at for item in snapshot.transactions)

    reopened = SqliteBankDataRepository(bank_data_repository.database_path)
    reopened.initialize()
    assert reopened.get_snapshot(session_id) == snapshot

    repeated = bank_data_service.get_or_materialize_snapshot(session_id)
    assert repeated == snapshot


def test_two_sessions_share_versioned_master_data_but_keep_separate_snapshots(
    client: TestClient,
    bank_data_service: BankDataService,
    bank_data_repository: SqliteBankDataRepository,
) -> None:
    first_session_id = create_session(client, "startup")
    second_session_id = create_session(client, "startup")

    first = bank_data_service.get_or_materialize_snapshot(first_session_id)
    second = bank_data_service.get_or_materialize_snapshot(second_session_id)

    assert first.session_id != second.session_id
    assert first.accounts == second.accounts
    assert first.balances == second.balances
    assert first.transactions == second.transactions
    assert len(first.transactions) == 12

    with sqlite3.connect(bank_data_repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM bank_account_balances").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM bank_transactions").fetchone()[0] == 12
        assert (
            connection.execute("SELECT COUNT(*) FROM bank_data_session_snapshots").fetchone()[0]
            == 2
        )


def test_bank_fixture_excludes_direct_identifiers_and_unverified_sales_labels(
    bank_data_service: BankDataService,
) -> None:
    fixture_text = bank_data_service.catalog.catalog_path.read_text(encoding="utf-8")

    excluded_fields = {
        "accountNumber",
        "accountHolderName",
        "printedContent",
        "counterpartyName",
        "isSalesDeposit",
    }
    assert all(field not in fixture_text for field in excluded_fields)
