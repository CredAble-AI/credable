import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from app.repositories.bank_data_repository import BankDataRepository
from app.repositories.credit_exposure_repository import CreditExposureRepository
from app.repositories.credit_history_repository import CreditHistoryRepository
from app.repositories.feature_snapshot_repository import FeatureSnapshotRepository
from app.repositories.loan_history_repository import LoanHistoryRepository
from app.schemas.assessment import AssessmentFeatureSnapshotReference, AssessmentSnapshotType
from app.schemas.bank_data import CreditDebitIndicator
from app.schemas.credit_exposure import (
    ExposureStatus,
    ExternalDelinquencyStatus,
    GuaranteeStatus,
)
from app.schemas.feature_snapshot import (
    AssessmentFeatureSnapshot,
    FeatureCode,
    FeatureValueStatus,
    FeatureValueType,
    NeutralFeatureValue,
)
from app.schemas.loan_history import DelinquencyStatus, LoanAccountStatus
from app.services.assessment_data_lineage_service import AssessmentDataLineageService


class FeatureSnapshotService:
    FEATURE_SET_VERSION = "demo-neutral-feature-set-v2"
    CALCULATION_VERSION = "demo-neutral-aggregation-v2"

    def __init__(
        self,
        repository: FeatureSnapshotRepository,
        data_lineage_service: AssessmentDataLineageService,
        bank_data_repository: BankDataRepository,
        credit_history_repository: CreditHistoryRepository,
        loan_history_repository: LoanHistoryRepository,
        credit_exposure_repository: CreditExposureRepository,
    ) -> None:
        self.repository = repository
        self.data_lineage_service = data_lineage_service
        self.bank_data_repository = bank_data_repository
        self.credit_history_repository = credit_history_repository
        self.loan_history_repository = loan_history_repository
        self.credit_exposure_repository = credit_exposure_repository

    def initialize(self) -> None:
        self.repository.initialize()

    def get_or_build(
        self,
        session_id: str,
        feature_cutoff_at: datetime | None = None,
    ) -> AssessmentFeatureSnapshot | None:
        feature_cutoff_at = feature_cutoff_at or datetime.now(UTC)
        if feature_cutoff_at.tzinfo is None:
            raise ValueError("featureCutoffAt must include a timezone")
        source_snapshots = self.data_lineage_service.list_references(session_id)
        if not source_snapshots:
            return None
        after_cutoff_types = {
            item.snapshot_type
            for item in source_snapshots
            if item.observed_at > feature_cutoff_at or item.loaded_at > feature_cutoff_at
        }
        source_lineage_hash = self._hash_json(
            [
                {
                    **item.model_dump(mode="json", by_alias=True),
                    "pointInTimeValid": item.snapshot_type not in after_cutoff_types,
                }
                for item in source_snapshots
            ]
        )
        existing = self.repository.get_by_lineage(
            session_id,
            self.FEATURE_SET_VERSION,
            source_lineage_hash,
        )
        if existing is not None:
            return existing

        feature_values = [
            *self._bank_data_features(session_id, after_cutoff_types),
            *self._credit_history_features(session_id, after_cutoff_types),
            *self._loan_history_features(session_id, after_cutoff_types),
            *self._credit_exposure_features(session_id, after_cutoff_types),
        ]
        identity = {
            "sessionId": session_id,
            "featureSetVersion": self.FEATURE_SET_VERSION,
            "sourceLineageHash": source_lineage_hash,
        }
        snapshot = AssessmentFeatureSnapshot(
            feature_snapshot_id=f"fts_{self._hash_json(identity)}",
            session_id=session_id,
            feature_set_version=self.FEATURE_SET_VERSION,
            calculated_at=datetime.now(UTC),
            feature_cutoff_at=feature_cutoff_at,
            source_lineage_hash=source_lineage_hash,
            source_snapshots=source_snapshots,
            feature_values=feature_values,
        )
        return self.repository.save(snapshot)

    def get_reference(
        self,
        snapshot: AssessmentFeatureSnapshot,
    ) -> AssessmentFeatureSnapshotReference:
        return AssessmentFeatureSnapshotReference(
            feature_snapshot_id=snapshot.feature_snapshot_id,
            feature_set_version=snapshot.feature_set_version,
            calculated_at=snapshot.calculated_at,
            feature_cutoff_at=snapshot.feature_cutoff_at,
            source_lineage_hash=snapshot.source_lineage_hash,
            snapshot_hash=self._hash_json(snapshot.model_dump(mode="json", by_alias=True)),
        )

    def _bank_data_features(
        self,
        session_id: str,
        after_cutoff_types: set[AssessmentSnapshotType],
    ) -> list[NeutralFeatureValue]:
        source_type = AssessmentSnapshotType.BANK_ACCOUNT_DATA
        definitions = (
            (FeatureCode.BANK_ACCOUNT_COUNT, FeatureValueType.COUNT),
            (FeatureCode.BANK_TRANSACTION_COUNT, FeatureValueType.COUNT),
            (FeatureCode.BANK_SNAPSHOT_CREDIT_AMOUNT, FeatureValueType.AMOUNT),
            (FeatureCode.BANK_SNAPSHOT_DEBIT_AMOUNT, FeatureValueType.AMOUNT),
            (FeatureCode.BANK_LATEST_BOOKED_BALANCE, FeatureValueType.AMOUNT),
        )
        if source_type in after_cutoff_types:
            return self._unavailable(
                source_type,
                definitions,
                FeatureValueStatus.SOURCE_AFTER_CUTOFF,
            )
        snapshot = self.bank_data_repository.get_snapshot(session_id)
        if snapshot is None:
            return self._unavailable(source_type, definitions)

        latest_balances = {}
        for balance in snapshot.balances:
            current = latest_balances.get(balance.account_id)
            if current is None or balance.as_of_at > current.as_of_at:
                latest_balances[balance.account_id] = balance
        credit_amounts = self._sum_by_currency(
            (item.amount, item.currency)
            for item in snapshot.transactions
            if item.credit_debit_indicator == CreditDebitIndicator.CREDIT
        )
        debit_amounts = self._sum_by_currency(
            (item.amount, item.currency)
            for item in snapshot.transactions
            if item.credit_debit_indicator == CreditDebitIndicator.DEBIT
        )
        balances = self._sum_by_currency(
            (item.booked_balance, item.currency) for item in latest_balances.values()
        )
        return [
            self._count(FeatureCode.BANK_ACCOUNT_COUNT, source_type, len(snapshot.accounts)),
            self._count(
                FeatureCode.BANK_TRANSACTION_COUNT,
                source_type,
                len(snapshot.transactions),
            ),
            *self._amounts(FeatureCode.BANK_SNAPSHOT_CREDIT_AMOUNT, source_type, credit_amounts),
            *self._amounts(FeatureCode.BANK_SNAPSHOT_DEBIT_AMOUNT, source_type, debit_amounts),
            *self._amounts(FeatureCode.BANK_LATEST_BOOKED_BALANCE, source_type, balances),
        ]

    def _credit_history_features(
        self,
        session_id: str,
        after_cutoff_types: set[AssessmentSnapshotType],
    ) -> list[NeutralFeatureValue]:
        source_type = AssessmentSnapshotType.BANK_CREDIT_HISTORY
        definitions = (
            (FeatureCode.BANK_APPLICATION_COUNT, FeatureValueType.COUNT),
            (FeatureCode.BANK_CREDIT_ASSESSMENT_COUNT, FeatureValueType.COUNT),
        )
        if source_type in after_cutoff_types:
            return self._unavailable(
                source_type,
                definitions,
                FeatureValueStatus.SOURCE_AFTER_CUTOFF,
            )
        snapshot = self.credit_history_repository.get_snapshot(session_id)
        if snapshot is None:
            return self._unavailable(source_type, definitions)
        return [
            self._count(
                FeatureCode.BANK_APPLICATION_COUNT,
                source_type,
                len(snapshot.applications),
            ),
            self._count(
                FeatureCode.BANK_CREDIT_ASSESSMENT_COUNT,
                source_type,
                len(snapshot.credit_assessments),
            ),
        ]

    def _loan_history_features(
        self,
        session_id: str,
        after_cutoff_types: set[AssessmentSnapshotType],
    ) -> list[NeutralFeatureValue]:
        source_type = AssessmentSnapshotType.BANK_LOAN_HISTORY
        definitions = (
            (FeatureCode.BANK_ACTIVE_LOAN_COUNT, FeatureValueType.COUNT),
            (FeatureCode.BANK_OUTSTANDING_PRINCIPAL, FeatureValueType.AMOUNT),
            (FeatureCode.BANK_CURED_DELINQUENCY_COUNT, FeatureValueType.COUNT),
        )
        if source_type in after_cutoff_types:
            return self._unavailable(
                source_type,
                definitions,
                FeatureValueStatus.SOURCE_AFTER_CUTOFF,
            )
        snapshot = self.loan_history_repository.get_snapshot(session_id)
        if snapshot is None:
            return self._unavailable(source_type, definitions)
        active_loans = [
            item for item in snapshot.loan_accounts if item.status == LoanAccountStatus.ACTIVE
        ]
        outstanding = self._sum_by_currency(
            (item.outstanding_principal_amount, item.currency) for item in active_loans
        )
        return [
            self._count(FeatureCode.BANK_ACTIVE_LOAN_COUNT, source_type, len(active_loans)),
            *self._amounts(FeatureCode.BANK_OUTSTANDING_PRINCIPAL, source_type, outstanding),
            self._count(
                FeatureCode.BANK_CURED_DELINQUENCY_COUNT,
                source_type,
                sum(item.status == DelinquencyStatus.CURED for item in snapshot.delinquency_events),
            ),
        ]

    def _credit_exposure_features(
        self,
        session_id: str,
        after_cutoff_types: set[AssessmentSnapshotType],
    ) -> list[NeutralFeatureValue]:
        source_type = AssessmentSnapshotType.EXTERNAL_CREDIT_EXPOSURE
        definitions = (
            (FeatureCode.EXTERNAL_ACTIVE_EXPOSURE_COUNT, FeatureValueType.COUNT),
            (FeatureCode.EXTERNAL_OUTSTANDING_BALANCE, FeatureValueType.AMOUNT),
            (FeatureCode.EXTERNAL_CURED_DELINQUENCY_COUNT, FeatureValueType.COUNT),
            (FeatureCode.EXTERNAL_ACTIVE_GUARANTEE_COUNT, FeatureValueType.COUNT),
        )
        if source_type in after_cutoff_types:
            return self._unavailable(
                source_type,
                definitions,
                FeatureValueStatus.SOURCE_AFTER_CUTOFF,
            )
        snapshot = self.credit_exposure_repository.get_snapshot(session_id)
        if snapshot is None:
            return self._unavailable(source_type, definitions)
        active_exposures = [
            item for item in snapshot.exposures if item.status == ExposureStatus.ACTIVE
        ]
        outstanding = self._sum_by_currency(
            (item.outstanding_balance, item.currency) for item in active_exposures
        )
        return [
            self._count(
                FeatureCode.EXTERNAL_ACTIVE_EXPOSURE_COUNT,
                source_type,
                len(active_exposures),
            ),
            *self._amounts(FeatureCode.EXTERNAL_OUTSTANDING_BALANCE, source_type, outstanding),
            self._count(
                FeatureCode.EXTERNAL_CURED_DELINQUENCY_COUNT,
                source_type,
                sum(
                    item.status == ExternalDelinquencyStatus.CURED
                    for item in snapshot.delinquencies
                ),
            ),
            self._count(
                FeatureCode.EXTERNAL_ACTIVE_GUARANTEE_COUNT,
                source_type,
                sum(item.status == GuaranteeStatus.ACTIVE for item in snapshot.guarantees),
            ),
        ]

    def _count(
        self,
        code: FeatureCode,
        source_type: AssessmentSnapshotType,
        value: int,
    ) -> NeutralFeatureValue:
        return NeutralFeatureValue(
            feature_code=code,
            source_snapshot_type=source_type,
            value_type=FeatureValueType.COUNT,
            status=FeatureValueStatus.AVAILABLE,
            numeric_value=Decimal(value),
            calculation_version=self.CALCULATION_VERSION,
        )

    def _amounts(
        self,
        code: FeatureCode,
        source_type: AssessmentSnapshotType,
        values: dict[str, Decimal],
    ) -> list[NeutralFeatureValue]:
        if not values:
            return [
                NeutralFeatureValue(
                    feature_code=code,
                    source_snapshot_type=source_type,
                    value_type=FeatureValueType.AMOUNT,
                    status=FeatureValueStatus.NO_RECORDS,
                    calculation_version=self.CALCULATION_VERSION,
                )
            ]
        return [
            NeutralFeatureValue(
                feature_code=code,
                source_snapshot_type=source_type,
                value_type=FeatureValueType.AMOUNT,
                status=FeatureValueStatus.AVAILABLE,
                numeric_value=value,
                currency=currency,
                calculation_version=self.CALCULATION_VERSION,
            )
            for currency, value in sorted(values.items())
        ]

    def _unavailable(
        self,
        source_type: AssessmentSnapshotType,
        definitions: tuple[tuple[FeatureCode, FeatureValueType], ...],
        status: FeatureValueStatus = FeatureValueStatus.SOURCE_NOT_AVAILABLE,
    ) -> list[NeutralFeatureValue]:
        return [
            NeutralFeatureValue(
                feature_code=code,
                source_snapshot_type=source_type,
                value_type=value_type,
                status=status,
                calculation_version=self.CALCULATION_VERSION,
            )
            for code, value_type in definitions
        ]

    @staticmethod
    def _sum_by_currency(values: Iterable[tuple[Decimal, str]]) -> dict[str, Decimal]:
        totals: defaultdict[str, Decimal] = defaultdict(Decimal)
        for amount, currency in values:
            totals[currency] += amount
        return dict(totals)

    @staticmethod
    def _hash_json(value: object) -> str:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode()).hexdigest()

    def readiness(self) -> dict[str, bool]:
        return {"feature_snapshot_repository": self.repository.is_ready()}
