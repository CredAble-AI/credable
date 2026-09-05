import sqlite3

from fastapi.testclient import TestClient

from app.repositories.credit_history_repository import SqliteCreditHistoryRepository
from app.schemas.credit_history import (
    CreditAssessmentType,
    LoanApplicationStatus,
    LoanDecisionOutcome,
)
from app.services.credit_history_service import CreditHistoryService


def create_session(client: TestClient, demo_profile_id: str) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def test_existing_application_preserves_decision_and_baseline_assessment(
    client: TestClient,
    credit_history_service: CreditHistoryService,
    credit_history_repository: SqliteCreditHistoryRepository,
) -> None:
    session_id = create_session(client, "small-business")

    snapshot = credit_history_service.get_or_materialize_snapshot(session_id)

    assert snapshot.source_type == "BANK_INTERNAL"
    assert snapshot.data_version == "synthetic-bank-data-v1"
    assert len(snapshot.applications) == 1
    application = snapshot.applications[0]
    assert application.status == LoanApplicationStatus.DECLINED
    assert application.requested_amount == 30_000_000
    assert application.product_id == "demo-working-capital"

    assert len(snapshot.decisions) == 1
    decision = snapshot.decisions[0]
    assert decision.outcome == LoanDecisionOutcome.DECLINED
    assert decision.reason_codes == [
        "DEMO_INFORMATION_GAP",
        "DEMO_RECENT_PERFORMANCE_NOT_REFLECTED",
    ]

    assert len(snapshot.credit_assessments) == 1
    assessment = snapshot.credit_assessments[0]
    assert assessment.assessment_type == CreditAssessmentType.APPLICATION
    assert assessment.application_id == application.application_id
    assert assessment.grade_code == "DEMO_GRADE_C"
    assert assessment.grade_scale_version == "demo-bank-grade-scale-v1"
    assert assessment.feature_cutoff_at <= assessment.assessed_at <= snapshot.observed_at

    reopened = SqliteCreditHistoryRepository(credit_history_repository.database_path)
    reopened.initialize()
    assert reopened.get_snapshot(session_id) == snapshot
    assert credit_history_service.get_or_materialize_snapshot(session_id) == snapshot


def test_new_inquiry_has_assessment_without_requiring_application_history(
    client: TestClient,
    credit_history_service: CreditHistoryService,
    credit_history_repository: SqliteCreditHistoryRepository,
) -> None:
    session_id = create_session(client, "startup")

    snapshot = credit_history_service.get_or_materialize_snapshot(session_id)

    assert snapshot.applications == []
    assert snapshot.decisions == []
    assert len(snapshot.credit_assessments) == 1
    assessment = snapshot.credit_assessments[0]
    assert assessment.assessment_type == CreditAssessmentType.PERIODIC
    assert assessment.application_id is None

    with sqlite3.connect(credit_history_repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM loan_applications").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM loan_decisions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM bank_credit_assessments").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM credit_history_session_snapshots").fetchone()[0]
            == 1
        )


def test_fixture_does_not_invent_numeric_scores_or_decision_thresholds(
    credit_history_service: CreditHistoryService,
) -> None:
    fixture_text = credit_history_service.catalog.catalog_path.read_text(encoding="utf-8")

    excluded_fields = {
        "scoreValue",
        "approvalThreshold",
        "probabilityOfDefault",
        "approvedAmount",
        "interestRate",
    }
    assert all(field not in fixture_text for field in excluded_fields)
