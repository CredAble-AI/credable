from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.assessment import AssessmentStatus
from app.schemas.product_condition import (
    DemoProductConditionCatalogData,
    ProductConditionAdapterInput,
    ProductConditionAdapterResult,
    ProductConditionStatus,
)


class ProductConditionAdapter(ABC):
    @abstractmethod
    def query(
        self,
        input_data: ProductConditionAdapterInput,
    ) -> ProductConditionAdapterResult:
        """Query one product without inventing policy outputs."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the adapter can return an explicit condition state."""


class UnconfiguredProductConditionAdapter(ProductConditionAdapter):
    def query(
        self,
        input_data: ProductConditionAdapterInput,
    ) -> ProductConditionAdapterResult:
        del input_data
        return ProductConditionAdapterResult(
            status=ProductConditionStatus.POLICY_NOT_CONFIGURED,
            reason_code="DEMO_PRODUCT_POLICY_NOT_CONFIGURED",
        )

    def is_ready(self) -> bool:
        return True


class DemoProductConditionAdapter(ProductConditionAdapter):
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoProductConditionCatalogData | None = None
        self._results: dict[tuple[str, str], ProductConditionAdapterResult] = {}

    def query(
        self,
        input_data: ProductConditionAdapterInput,
    ) -> ProductConditionAdapterResult:
        if input_data.assessment.status != AssessmentStatus.COMPLETED:
            return ProductConditionAdapterResult(
                status=ProductConditionStatus.INSUFFICIENT_DATA,
                reason_code="DEMO_ASSESSMENT_NOT_COMPLETED",
            )
        self._initialize()
        return self._results.get(
            (input_data.demo_profile_id, input_data.product.product_id),
            ProductConditionAdapterResult(
                status=ProductConditionStatus.POLICY_NOT_CONFIGURED,
                reason_code="DEMO_PRODUCT_POLICY_NOT_CONFIGURED",
            ),
        )

    def is_ready(self) -> bool:
        try:
            self._initialize()
        except (OSError, ValueError):
            return False
        return True

    def _initialize(self) -> None:
        if self._catalog is not None:
            return
        catalog = DemoProductConditionCatalogData.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self._catalog = catalog
        self._results = {
            (item.demo_profile_id, item.product_id): item.result for item in catalog.conditions
        }
