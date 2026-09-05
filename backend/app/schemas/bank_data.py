from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class BankAccountType(StrEnum):
    DEMAND_DEPOSIT = "DEMAND_DEPOSIT"
    SAVINGS = "SAVINGS"
    INVESTMENT = "INVESTMENT"


class BankAccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class CreditDebitIndicator(StrEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class BankAccount(ApiModel):
    account_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    institution_code: str = Field(min_length=1)
    account_type: BankAccountType
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    opened_on: date
    closed_on: date | None = None
    status: BankAccountStatus

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "BankAccount":
        if self.closed_on is not None and self.closed_on < self.opened_on:
            raise ValueError("closedOn must not precede openedOn")
        if self.status == BankAccountStatus.ACTIVE and self.closed_on is not None:
            raise ValueError("active account cannot include closedOn")
        if self.status == BankAccountStatus.CLOSED and self.closed_on is None:
            raise ValueError("closed account requires closedOn")
        return self


class BankBalanceSnapshot(ApiModel):
    account_id: str = Field(min_length=1)
    as_of_at: datetime
    booked_balance: Decimal
    available_balance: Decimal | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_timestamp(self) -> "BankBalanceSnapshot":
        if self.as_of_at.tzinfo is None:
            raise ValueError("asOfAt must include a timezone")
        return self


class BankTransaction(ApiModel):
    transaction_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    booked_at: datetime
    value_date: date | None = None
    credit_debit_indicator: CreditDebitIndicator
    amount: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    balance_after: Decimal | None = None
    transaction_type_code: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_timestamp(self) -> "BankTransaction":
        if self.booked_at.tzinfo is None:
            raise ValueError("bookedAt must include a timezone")
        return self


class DemoBankDataProfile(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    observed_at: datetime
    accounts: list[BankAccount] = Field(min_length=1)
    balances: list[BankBalanceSnapshot] = Field(min_length=1)
    transactions: list[BankTransaction]

    @model_validator(mode="after")
    def validate_references_and_cutoff(self) -> "DemoBankDataProfile":
        if self.observed_at.tzinfo is None:
            raise ValueError("observedAt must include a timezone")

        account_ids = [account.account_id for account in self.accounts]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("accountId values must be unique within a profile")
        transaction_ids = [item.transaction_id for item in self.transactions]
        if len(transaction_ids) != len(set(transaction_ids)):
            raise ValueError("transactionId values must be unique within a profile")

        accounts_by_id = {account.account_id: account for account in self.accounts}
        for account in self.accounts:
            if account.borrower_id != self.borrower_id:
                raise ValueError("account borrowerId must match profile borrowerId")
            if account.primary_business_id != self.primary_business_id:
                raise ValueError("account primaryBusinessId must match profile")

        for balance in self.balances:
            account = accounts_by_id.get(balance.account_id)
            if account is None:
                raise ValueError("balance references an unknown accountId")
            if balance.currency != account.currency:
                raise ValueError("balance currency must match account currency")
            if balance.as_of_at > self.observed_at:
                raise ValueError("balance cannot be later than observedAt")

        for transaction in self.transactions:
            account = accounts_by_id.get(transaction.account_id)
            if account is None:
                raise ValueError("transaction references an unknown accountId")
            if transaction.currency != account.currency:
                raise ValueError("transaction currency must match account currency")
            if transaction.booked_at > self.observed_at:
                raise ValueError("transaction cannot be later than observedAt")
        return self


class DemoBankDataCatalog(ApiModel):
    data_version: str = Field(min_length=1)
    profiles: list[DemoBankDataProfile] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_profiles(self) -> "DemoBankDataCatalog":
        profile_ids = [profile.demo_profile_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("demoProfileId values must be unique")
        return self


class BankDataSnapshot(ApiModel):
    session_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    source_type: Literal["BANK_INTERNAL"] = "BANK_INTERNAL"
    observed_at: datetime
    loaded_at: datetime
    data_version: str = Field(min_length=1)
    accounts: list[BankAccount]
    balances: list[BankBalanceSnapshot]
    transactions: list[BankTransaction]
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_timestamps(self) -> "BankDataSnapshot":
        if self.observed_at.tzinfo is None or self.loaded_at.tzinfo is None:
            raise ValueError("bank data timestamps must include a timezone")
        return self
