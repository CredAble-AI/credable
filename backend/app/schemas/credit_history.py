from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class LoanApplicationStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"
    CANCELLED = "CANCELLED"


class LoanDecisionOutcome(StrEnum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    HELD = "HELD"


class CreditAssessmentType(StrEnum):
    APPLICATION = "APPLICATION"
    PERIODIC = "PERIODIC"
    ON_DEMAND = "ON_DEMAND"


class LoanApplication(ApiModel):
    application_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    product_id: str | None = Field(default=None, min_length=1)
    submitted_at: datetime
    requested_amount: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    requested_term_months: int | None = Field(default=None, gt=0)
    status: LoanApplicationStatus
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "LoanApplication":
        if self.submitted_at.tzinfo is None:
            raise ValueError("submittedAt must include a timezone")
        if self.resolved_at is not None:
            if self.resolved_at.tzinfo is None:
                raise ValueError("resolvedAt must include a timezone")
            if self.resolved_at < self.submitted_at:
                raise ValueError("resolvedAt must not precede submittedAt")
        terminal_statuses = {
            LoanApplicationStatus.APPROVED,
            LoanApplicationStatus.DECLINED,
            LoanApplicationStatus.WITHDRAWN,
            LoanApplicationStatus.CANCELLED,
        }
        if self.status in terminal_statuses and self.resolved_at is None:
            raise ValueError("terminal application status requires resolvedAt")
        if self.status not in terminal_statuses and self.resolved_at is not None:
            raise ValueError("active application status cannot include resolvedAt")
        return self


class LoanDecision(ApiModel):
    decision_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    outcome: LoanDecisionOutcome
    decided_at: datetime
    reason_codes: list[str] = Field(default_factory=list)
    policy_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision(self) -> "LoanDecision":
        if self.decided_at.tzinfo is None:
            raise ValueError("decidedAt must include a timezone")
        if any(not code.strip() for code in self.reason_codes):
            raise ValueError("reasonCodes cannot contain blank values")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reasonCodes must be unique")
        if self.outcome != LoanDecisionOutcome.APPROVED and not self.reason_codes:
            raise ValueError("declined or held decision requires reasonCodes")
        return self


class BankCreditAssessment(ApiModel):
    credit_assessment_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    application_id: str | None = Field(default=None, min_length=1)
    assessment_type: CreditAssessmentType
    assessed_at: datetime
    feature_cutoff_at: datetime
    grade_code: str = Field(min_length=1)
    grade_scale_version: str = Field(min_length=1)
    reason_codes: list[str] = Field(default_factory=list)
    model_version: str = Field(min_length=1)
    feature_set_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment(self) -> "BankCreditAssessment":
        if self.assessed_at.tzinfo is None or self.feature_cutoff_at.tzinfo is None:
            raise ValueError("assessment timestamps must include a timezone")
        if self.feature_cutoff_at > self.assessed_at:
            raise ValueError("featureCutoffAt cannot be later than assessedAt")
        if self.assessment_type == CreditAssessmentType.APPLICATION and self.application_id is None:
            raise ValueError("APPLICATION assessment requires applicationId")
        if (
            self.assessment_type != CreditAssessmentType.APPLICATION
            and self.application_id is not None
        ):
            raise ValueError("non-application assessment cannot include applicationId")
        if any(not code.strip() for code in self.reason_codes):
            raise ValueError("reasonCodes cannot contain blank values")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reasonCodes must be unique")
        return self


class DemoCreditHistoryProfile(ApiModel):
    demo_profile_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    observed_at: datetime
    applications: list[LoanApplication]
    decisions: list[LoanDecision]
    credit_assessments: list[BankCreditAssessment] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> "DemoCreditHistoryProfile":
        if self.observed_at.tzinfo is None:
            raise ValueError("observedAt must include a timezone")

        application_ids = [item.application_id for item in self.applications]
        decision_ids = [item.decision_id for item in self.decisions]
        assessment_ids = [item.credit_assessment_id for item in self.credit_assessments]
        if len(application_ids) != len(set(application_ids)):
            raise ValueError("applicationId values must be unique")
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("decisionId values must be unique")
        if len(assessment_ids) != len(set(assessment_ids)):
            raise ValueError("creditAssessmentId values must be unique")

        applications_by_id = {item.application_id: item for item in self.applications}
        for application in self.applications:
            if application.borrower_id != self.borrower_id:
                raise ValueError("application borrowerId must match profile")
            if application.primary_business_id != self.primary_business_id:
                raise ValueError("application primaryBusinessId must match profile")
            if application.submitted_at > self.observed_at:
                raise ValueError("application cannot be later than observedAt")

        decisions_by_application: dict[str, list[LoanDecision]] = {}
        for decision in self.decisions:
            application = applications_by_id.get(decision.application_id)
            if application is None:
                raise ValueError("decision references an unknown applicationId")
            if decision.decided_at < application.submitted_at:
                raise ValueError("decision cannot precede application submission")
            if decision.decided_at > self.observed_at:
                raise ValueError("decision cannot be later than observedAt")
            decisions_by_application.setdefault(decision.application_id, []).append(decision)

        for application in self.applications:
            if (
                application.status
                in {
                    LoanApplicationStatus.APPROVED,
                    LoanApplicationStatus.DECLINED,
                }
                and application.application_id not in decisions_by_application
            ):
                raise ValueError("approved or declined application requires a decision")

        for application_id, decisions in decisions_by_application.items():
            application = applications_by_id[application_id]
            latest_decision = max(decisions, key=lambda item: item.decided_at)
            expected_status = {
                LoanDecisionOutcome.APPROVED: LoanApplicationStatus.APPROVED,
                LoanDecisionOutcome.DECLINED: LoanApplicationStatus.DECLINED,
                LoanDecisionOutcome.HELD: LoanApplicationStatus.UNDER_REVIEW,
            }[latest_decision.outcome]
            if application.status != expected_status:
                raise ValueError("latest decision outcome must match application status")

        for assessment in self.credit_assessments:
            if assessment.borrower_id != self.borrower_id:
                raise ValueError("assessment borrowerId must match profile")
            if assessment.primary_business_id != self.primary_business_id:
                raise ValueError("assessment primaryBusinessId must match profile")
            if assessment.application_id not in {None, *applications_by_id}:
                raise ValueError("assessment references an unknown applicationId")
            if assessment.assessed_at > self.observed_at:
                raise ValueError("assessment cannot be later than observedAt")
        return self


class DemoCreditHistoryCatalog(ApiModel):
    data_version: str = Field(min_length=1)
    profiles: list[DemoCreditHistoryProfile] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_profiles(self) -> "DemoCreditHistoryCatalog":
        profile_ids = [profile.demo_profile_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("demoProfileId values must be unique")
        return self


class CreditHistorySnapshot(ApiModel):
    session_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    primary_business_id: str | None = None
    source_type: Literal["BANK_INTERNAL"] = "BANK_INTERNAL"
    observed_at: datetime
    loaded_at: datetime
    data_version: str = Field(min_length=1)
    applications: list[LoanApplication]
    decisions: list[LoanDecision]
    credit_assessments: list[BankCreditAssessment]
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_timestamps(self) -> "CreditHistorySnapshot":
        if self.observed_at.tzinfo is None or self.loaded_at.tzinfo is None:
            raise ValueError("credit history timestamps must include a timezone")
        return self
