import sqlite3

from fastapi.testclient import TestClient

from app.repositories.credit_exposure_repository import SqliteCreditExposureRepository
from app.schemas.credit_exposure import (
    ExposureSecurityType,
    ExternalDelinquencyStatus,
    GuaranteeStatus,
)
from app.services.credit_exposure_service import CreditExposureService


def create_session(client: TestClient, demo_profile_id: str) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def test_external_credit_report_preserves_exposure_delinquency_and_guarantee_facts(
    client: TestClient,
    credit_exposure_service: CreditExposureService,
    credit_exposure_repository: SqliteCreditExposureRepository,
) -> None:
    session_id = create_session(client, "small-business")

    snapshot = credit_exposure_service.get_or_materialize_snapshot(session_id)

    assert snapshot.source_type == "CREDIT_INFORMATION"
    assert snapshot.data_version == "synthetic-credit-information-v1"
    assert snapshot.provider_code == "DEMO_CREDIT_INFORMATION_PROVIDER"
    assert len(snapshot.exposures) == 1
    exposure = snapshot.exposures[0]
    assert exposure.outstanding_balance == 8_000_000
    assert exposure.annual_interest_rate_percent is None
    assert exposure.security_type == ExposureSecurityType.GUARANTEE

    assert len(snapshot.delinquencies) == 1
    assert snapshot.delinquencies[0].status == ExternalDelinquencyStatus.CURED
    assert snapshot.delinquencies[0].max_days_past_due == 2
    assert len(snapshot.guarantees) == 1
    assert snapshot.guarantees[0].status == GuaranteeStatus.ACTIVE

    reopened = SqliteCreditExposureRepository(credit_exposure_repository.database_path)
    reopened.initialize()
    assert reopened.get_snapshot(session_id) == snapshot
    assert credit_exposure_service.get_or_materialize_snapshot(session_id) == snapshot


def test_verified_report_can_preserve_no_external_credit_exposure(
    client: TestClient,
    credit_exposure_service: CreditExposureService,
    credit_exposure_repository: SqliteCreditExposureRepository,
) -> None:
    session_id = create_session(client, "startup")

    snapshot = credit_exposure_service.get_or_materialize_snapshot(session_id)

    assert snapshot.exposures == []
    assert snapshot.delinquencies == []
    assert snapshot.guarantees == []
    with sqlite3.connect(credit_exposure_repository.database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM external_credit_exposures").fetchone()[0] == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM credit_exposure_session_snapshots").fetchone()[
                0
            ]
            == 1
        )


def test_fixture_avoids_derived_total_debt_score_and_policy_values(
    credit_exposure_service: CreditExposureService,
) -> None:
    fixture_text = credit_exposure_service.catalog.catalog_path.read_text(encoding="utf-8")

    excluded_fields = {
        "totalDebt",
        "creditScore",
        "riskGrade",
        "probabilityOfDefault",
        "approvalThreshold",
        "approvedAmount",
    }
    assert all(field not in fixture_text for field in excluded_fields)
