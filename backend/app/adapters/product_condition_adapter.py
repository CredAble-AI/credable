from abc import ABC, abstractmethod

from app.schemas.product_condition import (
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
