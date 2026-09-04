from abc import ABC, abstractmethod
from pathlib import Path

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


class DemoProductCatalogAdapter(ProductCatalogAdapter):
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path

    @property
    def adapter_version(self) -> str:
        return "demo-product-catalog-adapter-v1"

    def load(self) -> ProductCatalogAdapterResult:
        return ProductCatalogAdapterResult.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )

    def is_ready(self) -> bool:
        try:
            self.load()
        except (OSError, ValueError):
            return False
        return True
