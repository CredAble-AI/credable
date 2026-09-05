from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class InstitutionSector(StrEnum):
    BANK = "BANK"
    SAVINGS_BANK = "SAVINGS_BANK"
    CARD = "CARD"
    CAPITAL = "CAPITAL"
    INSURANCE = "INSURANCE"
    GUARANTEE_INSTITUTION = "GUARANTEE_INSTITUTION"
    OTHER = "OTHER"


class ExposureProductType(StrEnum):
    BUSINESS_LOAN = "BUSINESS_LOAN"
    CREDIT_LOAN = "CREDIT_LOAN"
    CARD_LOAN = "CARD_LOAN"
    INSURANCE_POLICY_LOAN = "INSURANCE_POLICY_LOAN"
    OTHER = "OTHER"


class ExposureSecurityType(StrEnum):
    UNSECURED = "UNSECURED"
    GUARANTEE = "GUARANTEE"
    COLLATERAL = "COLLATERAL"
    OTHER = "OTHER"


class ExposureStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class ExternalDelinquencyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CURED = "CURED"


class GuaranteeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    RELEASED = "RELEASED"


class ExternalCreditExposure(ApiModel):
    exposure_id: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    reporting_institution_code: str = Field(min_length=1)
    institution_sector: InstitutionSector
    product_type: ExposureProductType
    opened_on: date
    maturity_on: date | None = None
    original_principal_amount: Decimal | None = Field(default=None, gt=0)
    outstanding_balance: Decimal = Field(ge=0)
    annual_interest_rate_percent: Decimal | None = Field(default=None, ge=0, le=100)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    security_type: ExposureSecurityType
    status: ExposureStatus

    @model_validator(mode="after")
    def validate_exposure(self) -> "ExternalCreditExposure":
        if self.maturity_on is not None and self.maturity_on < self.opened_on:
            raise ValueError("maturityOn must not precede openedOn")
        if (
            self.original_principal_amount is not None
            and self.outstanding_balance > self.original_principal_amount
        ):
            raise ValueError("outstandingBalance cannot exceed originalPrincipalAmount")
        if self.status == ExposureStatus.CLOSED and self.outstanding_balance != 0:
            raise ValueError("closed exposure must have zero outstanding balance")
        return self


class ExternalCreditDelinquency(ApiModel):
    delinquency_id: str = Field(min_length=1)
    exposure_id: str = Field(min_length=1)
    started_on: date
    cured_on: date | None = None
    max_days_past_due: int = Field(gt=0)
    overdue_principal_amount: Decimal = Field(ge=0)
    overdue_interest_amount: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: ExternalDelinquencyStatus
    reason_code: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "ExternalCreditDelinquency":
        if self.cured_on is not None and self.cured_on < self.started_on:
            raise ValueError("curedOn must not precede startedOn")
        if self.status == ExternalDelinquencyStatus.ACTIVE and self.cured_on is not None:
            raise ValueError("active delinquency cannot include curedOn")
        if self.status == ExternalDelinquencyStatus.CURED and self.cured_on is None:
            raise ValueError("cured delinquency requires curedOn")
        if self.overdue_principal_amount + self.overdue_interest_amount <= 0:
            raise ValueError("delinquency must include a positive overdue amount")
        return self


class ExternalCreditGuarantee(ApiModel):
    guarantee_id: str = Field(min_length=1)
    exposure_id: str = Field(min_length=1)
    guarantor_institution_code: str = Field(min_length=1)
    guarantee_type_code: str = Field(min_length=1)
    started_on: date
    ended_on: date | None = None
    guaranteed_amount: Decimal = Field(gt=0)
    outstanding_guaranteed_amount: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: GuaranteeStatus

    @model_validator(mode="after")
    def validate_guarantee(self) -> "ExternalCreditGuarantee":
        if self.outstanding_guaranteed_amount > self.guaranteed_amount:
            raise ValueError("outstandingGuaranteedAmount cannot exceed guaranteedAmount")
        if self.ended_on is not None and self.ended_on < self.started_on:
            raise ValueError("endedOn must not precede startedOn")
        if self.status == GuaranteeStatus.ACTIVE and self.ended_on is not None:
            raise ValueError("active guarantee cannot include endedOn")
        if self.status != GuaranteeStatus.ACTIVE and self.ended_on is None:
            raise ValueError("inactive guarantee requires endedOn")
        return self


class DemoCreditExposureProfile(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    provider_code: str = Field(min_length=1)
    report_id: str = Field(min_length=1)
    reported_at: datetime
    exposures: list[ExternalCreditExposure]
    delinquencies: list[ExternalCreditDelinquency]
    guarantees: list[ExternalCreditGuarantee]

    @model_validator(mode="after")
    def validate_references(self) -> "DemoCreditExposureProfile":
        if self.reported_at.tzinfo is None:
            raise ValueError("reportedAt must include a timezone")

        exposure_ids = [item.exposure_id for item in self.exposures]
        source_record_ids = [item.source_record_id for item in self.exposures]
        delinquency_ids = [item.delinquency_id for item in self.delinquencies]
        guarantee_ids = [item.guarantee_id for item in self.guarantees]
        for values, label in (
            (exposure_ids, "exposureId"),
            (source_record_ids, "sourceRecordId"),
            (delinquency_ids, "delinquencyId"),
            (guarantee_ids, "guaranteeId"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} values must be unique")

        exposures_by_id = {item.exposure_id: item for item in self.exposures}
        guaranteed_exposure_ids: set[str] = set()
        for exposure in self.exposures:
            if exposure.borrower_id != self.borrower_id:
                raise ValueError("exposure borrowerId must match profile")
            if exposure.primary_business_id != self.primary_business_id:
                raise ValueError("exposure primaryBusinessId must match profile")
            if exposure.opened_on > self.reported_at.date():
                raise ValueError("exposure cannot open after reportedAt")

        for delinquency in self.delinquencies:
            exposure = exposures_by_id.get(delinquency.exposure_id)
            if exposure is None:
                raise ValueError("delinquency references an unknown exposureId")
            if delinquency.currency != exposure.currency:
                raise ValueError("delinquency currency must match exposure")
            if delinquency.started_on < exposure.opened_on:
                raise ValueError("delinquency cannot precede exposure opening")
            if delinquency.started_on > self.reported_at.date():
                raise ValueError("delinquency cannot start after reportedAt")
            if delinquency.cured_on is not None and delinquency.cured_on > self.reported_at.date():
                raise ValueError("delinquency cure cannot be later than reportedAt")

        for guarantee in self.guarantees:
            exposure = exposures_by_id.get(guarantee.exposure_id)
            if exposure is None:
                raise ValueError("guarantee references an unknown exposureId")
            if guarantee.currency != exposure.currency:
                raise ValueError("guarantee currency must match exposure")
            if guarantee.started_on < exposure.opened_on:
                raise ValueError("guarantee cannot precede exposure opening")
            guaranteed_exposure_ids.add(guarantee.exposure_id)

        for exposure in self.exposures:
            if (
                exposure.security_type == ExposureSecurityType.GUARANTEE
                and exposure.exposure_id not in guaranteed_exposure_ids
            ):
                raise ValueError("guaranteed exposure requires a guarantee record")
        return self


class DemoCreditExposureCatalog(ApiModel):
    data_version: str = Field(min_length=1)
    profiles: list[DemoCreditExposureProfile] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_profiles(self) -> "DemoCreditExposureCatalog":
        profile_ids = [profile.demo_profile_id for profile in self.profiles]
        report_ids = [profile.report_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("demoProfileId values must be unique")
        if len(report_ids) != len(set(report_ids)):
            raise ValueError("reportId values must be unique")
        return self


class CreditExposureSnapshot(ApiModel):
    session_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    source_type: Literal["CREDIT_INFORMATION"] = "CREDIT_INFORMATION"
    provider_code: str = Field(min_length=1)
    report_id: str = Field(min_length=1)
    reported_at: datetime
    loaded_at: datetime
    data_version: str = Field(min_length=1)
    exposures: list[ExternalCreditExposure]
    delinquencies: list[ExternalCreditDelinquency]
    guarantees: list[ExternalCreditGuarantee]
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_timestamps(self) -> "CreditExposureSnapshot":
        if self.reported_at.tzinfo is None or self.loaded_at.tzinfo is None:
            raise ValueError("credit exposure timestamps must include a timezone")
        return self
