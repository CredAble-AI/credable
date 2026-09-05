from decimal import Decimal

from fastapi.testclient import TestClient

from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.feature_snapshot_repository import SqliteFeatureSnapshotRepository
from app.schemas.consent import ConsentSourceType
from app.schemas.feature_snapshot import FeatureCode, FeatureValueStatus
from app.services.data_source_service import DataSourceService
from app.services.feature_snapshot_service import FeatureSnapshotService


def create_session(client: TestClient, demo_profile_id: str) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def refresh_sources(
    client: TestClient,
    session_id: str,
    data_source_service: DataSourceService,
    source_types: tuple[ConsentSourceType, ...],
) -> None:
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    for source_type in source_types:
        response = client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant")
        assert response.status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200


def values_by_dimension(snapshot) -> dict[tuple[FeatureCode, str | None], object]:
    return {(item.feature_code, item.currency): item for item in snapshot.feature_values}


def test_builds_versioned_neutral_features_without_cross_source_totals(
    client: TestClient,
    data_source_service: DataSourceService,
    feature_snapshot_service: FeatureSnapshotService,
) -> None:
    session_id = create_session(client, "small-business")
    refresh_sources(
        client,
        session_id,
        data_source_service,
        (ConsentSourceType.BANK_INTERNAL, ConsentSourceType.CREDIT_INFORMATION),
    )

    snapshot = feature_snapshot_service.get_or_build(session_id)

    assert snapshot is not None
    assert snapshot.feature_snapshot_id.startswith("fts_")
    assert snapshot.feature_set_version == "demo-neutral-feature-set-v1"
    assert len(snapshot.source_snapshots) == 4
    values = values_by_dimension(snapshot)
    assert values[(FeatureCode.BANK_ACCOUNT_COUNT, None)].numeric_value == Decimal("1")
    assert values[(FeatureCode.BANK_TRANSACTION_COUNT, None)].numeric_value == Decimal("12")
    assert values[(FeatureCode.BANK_SNAPSHOT_CREDIT_AMOUNT, "KRW")].numeric_value == Decimal(
        "80600000"
    )
    assert values[(FeatureCode.BANK_SNAPSHOT_DEBIT_AMOUNT, "KRW")].numeric_value == Decimal(
        "76260000"
    )
    assert values[(FeatureCode.BANK_LATEST_BOOKED_BALANCE, "KRW")].numeric_value == Decimal(
        "7840000"
    )
    assert values[(FeatureCode.BANK_OUTSTANDING_PRINCIPAL, "KRW")].numeric_value == Decimal(
        "12000000"
    )
    assert values[(FeatureCode.EXTERNAL_OUTSTANDING_BALANCE, "KRW")].numeric_value == Decimal(
        "8000000"
    )
    codes = {item.feature_code.value for item in snapshot.feature_values}
    assert all(
        forbidden not in code
        for code in codes
        for forbidden in ("TOTAL_DEBT", "SCORE", "GRADE", "WEIGHT", "THRESHOLD")
    )


def test_distinguishes_verified_zero_records_from_missing_source(
    client: TestClient,
    data_source_service: DataSourceService,
    feature_snapshot_service: FeatureSnapshotService,
) -> None:
    session_id = create_session(client, "startup")
    refresh_sources(
        client,
        session_id,
        data_source_service,
        (ConsentSourceType.BANK_INTERNAL,),
    )

    snapshot = feature_snapshot_service.get_or_build(session_id)

    assert snapshot is not None
    values = values_by_dimension(snapshot)
    assert values[(FeatureCode.BANK_ACTIVE_LOAN_COUNT, None)].status == FeatureValueStatus.AVAILABLE
    assert values[(FeatureCode.BANK_ACTIVE_LOAN_COUNT, None)].numeric_value == 0
    assert (
        values[(FeatureCode.BANK_OUTSTANDING_PRINCIPAL, None)].status
        == FeatureValueStatus.NO_RECORDS
    )
    assert (
        values[(FeatureCode.EXTERNAL_ACTIVE_EXPOSURE_COUNT, None)].status
        == FeatureValueStatus.SOURCE_NOT_AVAILABLE
    )


def test_reuses_same_lineage_and_restores_exact_snapshot(
    client: TestClient,
    data_source_service: DataSourceService,
    feature_snapshot_service: FeatureSnapshotService,
    feature_snapshot_repository: SqliteFeatureSnapshotRepository,
) -> None:
    session_id = create_session(client, "small-business")
    refresh_sources(
        client,
        session_id,
        data_source_service,
        (ConsentSourceType.BANK_INTERNAL, ConsentSourceType.CREDIT_INFORMATION),
    )

    first = feature_snapshot_service.get_or_build(session_id)
    second = feature_snapshot_service.get_or_build(session_id)

    assert first is not None
    assert second == first
    reopened = SqliteFeatureSnapshotRepository(feature_snapshot_repository.database_path)
    reopened.initialize()
    assert reopened.get(first.feature_snapshot_id) == first
