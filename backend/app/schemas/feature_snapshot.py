from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.assessment import AssessmentDataSnapshotReference, AssessmentSnapshotType
from app.schemas.base import ApiModel


class FeatureValueStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NO_RECORDS = "NO_RECORDS"
    SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"


class FeatureValueType(StrEnum):
    COUNT = "COUNT"
    AMOUNT = "AMOUNT"


class FeatureCode(StrEnum):
    BANK_ACCOUNT_COUNT = "BANK_ACCOUNT_COUNT"
    BANK_TRANSACTION_COUNT = "BANK_TRANSACTION_COUNT"
    BANK_SNAPSHOT_CREDIT_AMOUNT = "BANK_SNAPSHOT_CREDIT_AMOUNT"
    BANK_SNAPSHOT_DEBIT_AMOUNT = "BANK_SNAPSHOT_DEBIT_AMOUNT"
    BANK_LATEST_BOOKED_BALANCE = "BANK_LATEST_BOOKED_BALANCE"
    BANK_APPLICATION_COUNT = "BANK_APPLICATION_COUNT"
    BANK_CREDIT_ASSESSMENT_COUNT = "BANK_CREDIT_ASSESSMENT_COUNT"
    BANK_ACTIVE_LOAN_COUNT = "BANK_ACTIVE_LOAN_COUNT"
    BANK_OUTSTANDING_PRINCIPAL = "BANK_OUTSTANDING_PRINCIPAL"
    BANK_CURED_DELINQUENCY_COUNT = "BANK_CURED_DELINQUENCY_COUNT"
    EXTERNAL_ACTIVE_EXPOSURE_COUNT = "EXTERNAL_ACTIVE_EXPOSURE_COUNT"
    EXTERNAL_OUTSTANDING_BALANCE = "EXTERNAL_OUTSTANDING_BALANCE"
    EXTERNAL_CURED_DELINQUENCY_COUNT = "EXTERNAL_CURED_DELINQUENCY_COUNT"
    EXTERNAL_ACTIVE_GUARANTEE_COUNT = "EXTERNAL_ACTIVE_GUARANTEE_COUNT"


class NeutralFeatureValue(ApiModel):
    feature_code: FeatureCode
    source_snapshot_type: AssessmentSnapshotType
    value_type: FeatureValueType
    status: FeatureValueStatus
    numeric_value: Decimal | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    calculation_version: str = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_value(self) -> "NeutralFeatureValue":
        if self.status == FeatureValueStatus.AVAILABLE:
            if self.numeric_value is None:
                raise ValueError("AVAILABLE feature requires numericValue")
        elif self.numeric_value is not None:
            raise ValueError("unavailable feature cannot include numericValue")

        if self.value_type == FeatureValueType.COUNT:
            if self.currency is not None:
                raise ValueError("COUNT feature cannot include currency")
            if self.numeric_value is not None:
                if self.numeric_value < 0:
                    raise ValueError("COUNT feature numericValue cannot be negative")
                if self.numeric_value != int(self.numeric_value):
                    raise ValueError("COUNT feature numericValue must be an integer")
        elif self.status == FeatureValueStatus.AVAILABLE and self.currency is None:
            raise ValueError("available AMOUNT feature requires currency")
        return self


class AssessmentFeatureSnapshot(ApiModel):
    feature_snapshot_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    feature_set_version: str = Field(min_length=1)
    calculated_at: datetime
    source_lineage_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_snapshots: list[AssessmentDataSnapshotReference] = Field(min_length=1)
    feature_values: list[NeutralFeatureValue] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_snapshot(self) -> "AssessmentFeatureSnapshot":
        if self.calculated_at.tzinfo is None:
            raise ValueError("calculatedAt must include a timezone")
        snapshot_types = [item.snapshot_type for item in self.source_snapshots]
        if len(snapshot_types) != len(set(snapshot_types)):
            raise ValueError("sourceSnapshots snapshotType values must be unique")
        dimensions = [(item.feature_code, item.currency) for item in self.feature_values]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("featureCode and currency dimensions must be unique")
        return self
