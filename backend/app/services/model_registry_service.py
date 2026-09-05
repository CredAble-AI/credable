from pathlib import Path

from app.schemas.assessment import AdapterAssessmentResult, AssessmentStatus
from app.schemas.model_registry import (
    DemoModelRegistryCatalogData,
    ModelGovernanceResolution,
    ModelRegistryEntry,
    ModelRole,
    OperationalState,
    ValidationStatus,
)


class DemoModelRegistryCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoModelRegistryCatalogData | None = None
        self._models: dict[str, ModelRegistryEntry] = {}

    @property
    def registry_version(self) -> str:
        return self._load().registry_version

    def get(self, model_version: str) -> ModelRegistryEntry | None:
        self._load()
        return self._models.get(model_version)

    def is_ready(self) -> bool:
        try:
            self._load()
        except (OSError, ValueError):
            return False
        return True

    def _load(self) -> DemoModelRegistryCatalogData:
        if self._catalog is None:
            self._catalog = DemoModelRegistryCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
            self._models = {item.model_version: item for item in self._catalog.models}
        return self._catalog


class ModelRegistryService:
    def __init__(self, catalog: DemoModelRegistryCatalog) -> None:
        self.catalog = catalog

    def govern(
        self,
        result: AdapterAssessmentResult,
        expected_role: ModelRole,
    ) -> tuple[AdapterAssessmentResult, ModelGovernanceResolution | None]:
        if result.status != AssessmentStatus.COMPLETED or result.model_version is None:
            return result, None

        entry = self.catalog.get(result.model_version)
        reason_code: str | None = None
        if entry is None:
            reason_code = "ASSESSMENT_MODEL_NOT_REGISTERED"
        elif entry.model_role != expected_role:
            reason_code = "ASSESSMENT_MODEL_ROLE_MISMATCH"
        elif (
            entry.operational_state == OperationalState.SUSPENDED
            or entry.validation_status == ValidationStatus.SUSPENDED
        ):
            reason_code = "ASSESSMENT_MODEL_SUSPENDED"

        resolution = ModelGovernanceResolution(
            requested_model_version=result.model_version,
            expected_role=expected_role,
            registry_version=self.catalog.registry_version,
            registered=entry is not None,
            allowed=reason_code is None,
            model_role=entry.model_role if entry is not None else None,
            feature_set_version=entry.feature_set_version if entry is not None else None,
            training_data_version=entry.training_data_version if entry is not None else None,
            policy_version=entry.policy_version if entry is not None else None,
            validation_status=entry.validation_status if entry is not None else None,
            operational_state=entry.operational_state if entry is not None else None,
            reason_code=reason_code,
        )
        if resolution.allowed:
            return result, resolution
        return (
            AdapterAssessmentResult(
                status=AssessmentStatus.FAILED,
                reason_code=resolution.reason_code,
            ),
            resolution,
        )

    def readiness(self) -> dict[str, bool]:
        return {"model_registry_catalog": self.catalog.is_ready()}
