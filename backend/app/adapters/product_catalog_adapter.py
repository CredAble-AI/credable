from abc import ABC, abstractmethod

from app.schemas.product import ProductCatalogAdapterResult, ProductCatalogStatus


class ProductCatalogAdapter(ABC):
    @property
    @abstractmethod
    def adapter_version(self) -> str:
        """Return the version of the configured catalog source."""

    @abstractmethod
    def load(self) -> ProductCatalogAdapterResult:
        """Load official bank products without personalizing their conditions."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Report whether the adapter can return an explicit catalog state."""


class UnconfiguredProductCatalogAdapter(ProductCatalogAdapter):
    @property
    def adapter_version(self) -> str:
        return "unconfigured-product-catalog-v1"

    def load(self) -> ProductCatalogAdapterResult:
        return ProductCatalogAdapterResult(
            status=ProductCatalogStatus.CATALOG_NOT_CONFIGURED,
            reason_code="DEMO_PRODUCT_CATALOG_NOT_CONFIGURED",
        )

    def is_ready(self) -> bool:
        return True
