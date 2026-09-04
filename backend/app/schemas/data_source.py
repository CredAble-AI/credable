from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType


class RetrievalStatus(StrEnum):
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    NOT_REQUESTED = "NOT_REQUESTED"
    RETRIEVED = "RETRIEVED"
    NO_DATA = "NO_DATA"
    FAILED = "FAILED"


class VerificationStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    STALE = "STALE"


class DataSourceState(ApiModel):
    source_type: ConsentSourceType
    display_name: str = Field(min_length=1)
    retrieval_status: RetrievalStatus
    verification_status: VerificationStatus
    observed_at: datetime | None = None
    retrieved_at: datetime | None = None
    data_version: str | None = None
    reason_code: str | None = None
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_state(self) -> "DataSourceState":
        timestamps = (self.observed_at, self.retrieved_at)
        if any(value is not None and value.tzinfo is None for value in timestamps):
            raise ValueError("data source timestamps must include a timezone")
        if self.retrieval_status == RetrievalStatus.RETRIEVED:
            if None in (self.observed_at, self.retrieved_at, self.data_version):
                raise ValueError("RETRIEVED data requires timestamps and dataVersion")
        elif self.observed_at is not None or self.data_version is not None:
            raise ValueError("non-retrieved state cannot include observed data metadata")
        if (
            self.retrieval_status
            in {
                RetrievalStatus.CONSENT_REQUIRED,
                RetrievalStatus.NOT_REQUESTED,
            }
            and self.retrieved_at is not None
        ):
            raise ValueError("unrequested data source cannot include retrievedAt")
        if (
            self.retrieval_status != RetrievalStatus.RETRIEVED
            and self.verification_status != VerificationStatus.NOT_STARTED
        ):
            raise ValueError("only retrieved data can have a verification result")
        if (
            self.retrieval_status
            in {
                RetrievalStatus.CONSENT_REQUIRED,
                RetrievalStatus.NO_DATA,
                RetrievalStatus.FAILED,
            }
            and not self.reason_code
        ):
            raise ValueError("blocked or unsuccessful retrieval requires reasonCode")
        return self


class DataSourceListResponse(ApiModel):
    session_id: str = Field(min_length=1)
    data_sources: list[DataSourceState]
    demo_only: Literal[True] = True


class AdapterRetrievalResult(ApiModel):
    retrieval_status: RetrievalStatus
    verification_status: VerificationStatus = VerificationStatus.NOT_STARTED
    observed_at: datetime | None = None
    data_version: str | None = None
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_adapter_result(self) -> "AdapterRetrievalResult":
        if self.retrieval_status not in {
            RetrievalStatus.RETRIEVED,
            RetrievalStatus.NO_DATA,
            RetrievalStatus.FAILED,
        }:
            raise ValueError("adapter must return a completed retrieval status")
        if self.retrieval_status == RetrievalStatus.RETRIEVED:
            if self.observed_at is None or self.data_version is None:
                raise ValueError("retrieved adapter result requires data metadata")
        elif self.observed_at is not None or self.data_version is not None:
            raise ValueError("adapter result without data cannot include data metadata")
        if (
            self.retrieval_status != RetrievalStatus.RETRIEVED
            and self.verification_status != VerificationStatus.NOT_STARTED
        ):
            raise ValueError("only retrieved adapter data can be verified")
        if (
            self.retrieval_status
            in {
                RetrievalStatus.NO_DATA,
                RetrievalStatus.FAILED,
            }
            and not self.reason_code
        ):
            raise ValueError("unsuccessful adapter result requires reasonCode")
        return self
