from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class ModelRole(StrEnum):
    BASELINE_ASSESSMENT = "BASELINE_ASSESSMENT"
    SUPPLEMENTAL_ASSESSMENT = "SUPPLEMENTAL_ASSESSMENT"


class ValidationStatus(StrEnum):
    DEMO_ONLY = "DEMO_ONLY"
    DEVELOPMENT = "DEVELOPMENT"
    INDEPENDENT_VALIDATION = "INDEPENDENT_VALIDATION"
    SHADOW = "SHADOW"
    LIMITED_PILOT = "LIMITED_PILOT"
    VALIDATED = "VALIDATED"
    SUSPENDED = "SUSPENDED"


class OperationalState(StrEnum):
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"


class ModelRegistryEntry(ApiModel):
    model_version: str = Field(min_length=1)
    model_role: ModelRole
    feature_set_version: str | None = Field(default=None, min_length=1)
    training_data_version: str | None = Field(default=None, min_length=1)
    policy_version: str | None = Field(default=None, min_length=1)
    validation_status: ValidationStatus
    operational_state: OperationalState
    demo_only: Literal[True] = True


class DemoModelRegistryCatalogData(ApiModel):
    registry_version: str = Field(min_length=1)
    models: list[ModelRegistryEntry] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_model_versions(self) -> "DemoModelRegistryCatalogData":
        versions = [item.model_version for item in self.models]
        if len(versions) != len(set(versions)):
            raise ValueError("modelVersion values must be unique")
        return self


class ModelGovernanceResolution(ApiModel):
    requested_model_version: str = Field(min_length=1)
    expected_role: ModelRole
    registry_version: str = Field(min_length=1)
    registered: bool
    allowed: bool
    model_role: ModelRole | None = None
    feature_set_version: str | None = None
    training_data_version: str | None = None
    policy_version: str | None = None
    validation_status: ValidationStatus | None = None
    operational_state: OperationalState | None = None
    reason_code: str | None = None
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_resolution(self) -> "ModelGovernanceResolution":
        if self.allowed and (not self.registered or self.reason_code is not None):
            raise ValueError("allowed model resolution must be registered without a reasonCode")
        if not self.allowed and self.reason_code is None:
            raise ValueError("blocked model resolution requires reasonCode")
        return self
