from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class LoanAccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class RepaymentScheduleStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class DelinquencyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CURED = "CURED"


class LoanAccount(ApiModel):
    loan_account_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    product_id: str | None = Field(default=None, min_length=1)
    originated_on: date
    maturity_on: date | None = None
    original_principal_amount: Decimal = Field(gt=0)
    outstanding_principal_amount: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: LoanAccountStatus

    @model_validator(mode="after")
    def validate_account(self) -> "LoanAccount":
        if self.maturity_on is not None and self.maturity_on < self.originated_on:
            raise ValueError("maturityOn must not precede originatedOn")
        if self.outstanding_principal_amount > self.original_principal_amount:
            raise ValueError("outstandingPrincipalAmount cannot exceed originalPrincipalAmount")
        if self.status == LoanAccountStatus.CLOSED and self.outstanding_principal_amount != 0:
            raise ValueError("closed loan account must have zero outstanding principal")
        return self


class RepaymentScheduleItem(ApiModel):
    schedule_id: str = Field(min_length=1)
    loan_account_id: str = Field(min_length=1)
    due_on: date
    scheduled_principal_amount: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: RepaymentScheduleStatus


class RepaymentEvent(ApiModel):
    repayment_event_id: str = Field(min_length=1)
    loan_account_id: str = Field(min_length=1)
    schedule_id: str | None = Field(default=None, min_length=1)
    paid_at: datetime
    principal_paid_amount: Decimal = Field(ge=0)
    interest_paid_amount: Decimal = Field(default=Decimal("0"), ge=0)
    fee_paid_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_transaction_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_payment(self) -> "RepaymentEvent":
        if self.paid_at.tzinfo is None:
            raise ValueError("paidAt must include a timezone")
        if self.principal_paid_amount + self.interest_paid_amount + self.fee_paid_amount <= 0:
            raise ValueError("repayment event must contain a positive paid amount")
        return self


class DelinquencyEvent(ApiModel):
    delinquency_event_id: str = Field(min_length=1)
    loan_account_id: str = Field(min_length=1)
    schedule_id: str | None = Field(default=None, min_length=1)
    started_at: datetime
    cured_at: datetime | None = None
    max_days_past_due: int = Field(gt=0)
    overdue_principal_amount: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: DelinquencyStatus

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "DelinquencyEvent":
        if self.started_at.tzinfo is None:
            raise ValueError("startedAt must include a timezone")
        if self.cured_at is not None:
            if self.cured_at.tzinfo is None:
                raise ValueError("curedAt must include a timezone")
            if self.cured_at < self.started_at:
                raise ValueError("curedAt must not precede startedAt")
        if self.status == DelinquencyStatus.ACTIVE and self.cured_at is not None:
            raise ValueError("active delinquency cannot include curedAt")
        if self.status == DelinquencyStatus.CURED and self.cured_at is None:
            raise ValueError("cured delinquency requires curedAt")
        return self


class DemoLoanHistoryProfile(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    observed_at: datetime
    loan_accounts: list[LoanAccount]
    repayment_schedules: list[RepaymentScheduleItem]
    repayment_events: list[RepaymentEvent]
    delinquency_events: list[DelinquencyEvent]

    @model_validator(mode="after")
    def validate_references(self) -> "DemoLoanHistoryProfile":
        if self.observed_at.tzinfo is None:
            raise ValueError("observedAt must include a timezone")

        account_ids = [item.loan_account_id for item in self.loan_accounts]
        schedule_ids = [item.schedule_id for item in self.repayment_schedules]
        repayment_ids = [item.repayment_event_id for item in self.repayment_events]
        delinquency_ids = [item.delinquency_event_id for item in self.delinquency_events]
        for values, label in (
            (account_ids, "loanAccountId"),
            (schedule_ids, "scheduleId"),
            (repayment_ids, "repaymentEventId"),
            (delinquency_ids, "delinquencyEventId"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} values must be unique")

        accounts_by_id = {item.loan_account_id: item for item in self.loan_accounts}
        schedules_by_id = {item.schedule_id: item for item in self.repayment_schedules}
        for account in self.loan_accounts:
            if account.borrower_id != self.borrower_id:
                raise ValueError("loan account borrowerId must match profile")
            if account.primary_business_id != self.primary_business_id:
                raise ValueError("loan account primaryBusinessId must match profile")
            if account.originated_on > self.observed_at.date():
                raise ValueError("loan account cannot originate after observedAt")

        for schedule in self.repayment_schedules:
            account = accounts_by_id.get(schedule.loan_account_id)
            if account is None:
                raise ValueError("repayment schedule references an unknown loanAccountId")
            if schedule.currency != account.currency:
                raise ValueError("repayment schedule currency must match loan account")
            if schedule.due_on < account.originated_on:
                raise ValueError("repayment schedule cannot precede loan origination")
            if account.maturity_on is not None and schedule.due_on > account.maturity_on:
                raise ValueError("repayment schedule cannot follow loan maturity")

        for repayment in self.repayment_events:
            account = accounts_by_id.get(repayment.loan_account_id)
            if account is None:
                raise ValueError("repayment event references an unknown loanAccountId")
            if repayment.schedule_id is not None:
                schedule = schedules_by_id.get(repayment.schedule_id)
                if schedule is None or schedule.loan_account_id != repayment.loan_account_id:
                    raise ValueError("repayment event references an incompatible scheduleId")
            if repayment.currency != account.currency:
                raise ValueError("repayment event currency must match loan account")
            if repayment.paid_at > self.observed_at:
                raise ValueError("repayment event cannot be later than observedAt")

        for delinquency in self.delinquency_events:
            account = accounts_by_id.get(delinquency.loan_account_id)
            if account is None:
                raise ValueError("delinquency event references an unknown loanAccountId")
            if delinquency.schedule_id is not None:
                schedule = schedules_by_id.get(delinquency.schedule_id)
                if schedule is None or schedule.loan_account_id != delinquency.loan_account_id:
                    raise ValueError("delinquency event references an incompatible scheduleId")
            if delinquency.currency != account.currency:
                raise ValueError("delinquency event currency must match loan account")
            if delinquency.started_at > self.observed_at:
                raise ValueError("delinquency event cannot be later than observedAt")
            if delinquency.cured_at is not None and delinquency.cured_at > self.observed_at:
                raise ValueError("delinquency cure cannot be later than observedAt")
        return self


class DemoLoanHistoryCatalog(ApiModel):
    data_version: str = Field(min_length=1)
    profiles: list[DemoLoanHistoryProfile] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_profiles(self) -> "DemoLoanHistoryCatalog":
        profile_ids = [profile.demo_profile_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("demoProfileId values must be unique")
        return self


class LoanHistorySnapshot(ApiModel):
    session_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    source_type: Literal["BANK_INTERNAL"] = "BANK_INTERNAL"
    observed_at: datetime
    loaded_at: datetime
    data_version: str = Field(min_length=1)
    loan_accounts: list[LoanAccount]
    repayment_schedules: list[RepaymentScheduleItem]
    repayment_events: list[RepaymentEvent]
    delinquency_events: list[DelinquencyEvent]
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_timestamps(self) -> "LoanHistorySnapshot":
        if self.observed_at.tzinfo is None or self.loaded_at.tzinfo is None:
            raise ValueError("loan history timestamps must include a timezone")
        return self
