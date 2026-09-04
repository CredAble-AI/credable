import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.adapters.product_catalog_adapter import ProductCatalogAdapter
from app.repositories.product_catalog_repository import ProductCatalogRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.product import (
    ProductCatalogAdapterResult,
    ProductCatalogResponse,
    ProductCatalogState,
    ProductCatalogStatus,
)
from app.services.session_service import CustomerSessionService


class ProductCatalogService:
    def __init__(
        self,
        repository: ProductCatalogRepository,
        session_service: CustomerSessionService,
        adapter: ProductCatalogAdapter,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.adapter = adapter

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> ProductCatalogResponse:
        self.session_service.get_session(session_id)
        state = self.repository.get_latest(session_id)
        if state is None:
            state = ProductCatalogState(status=ProductCatalogStatus.NOT_LOADED)
        return ProductCatalogResponse(session_id=session_id, catalog=state)

    def refresh(self, session_id: str, request_id: str) -> ProductCatalogResponse:
        self.session_service.get_session(session_id)
        try:
            result = self.adapter.load()
        except Exception:
            result = ProductCatalogAdapterResult(
                status=ProductCatalogStatus.FAILED,
                reason_code="PRODUCT_CATALOG_ADAPTER_ERROR",
            )

        retrieved_at = datetime.now(UTC)
        content = result.model_dump(mode="json", by_alias=True)
        content_json = json.dumps(
            content,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        content_hash = hashlib.sha256(content_json.encode()).hexdigest()
        state = ProductCatalogState(
            status=result.status,
            catalog_snapshot_id=f"pcs_{content_hash}",
            products=result.products,
            retrieved_at=retrieved_at,
            catalog_version=result.catalog_version,
            reason_code=result.reason_code,
        )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.PRODUCT_CATALOG_REFRESHED,
            timestamp=retrieved_at,
            actor=AuditActor.SYSTEM,
            input_version=self.adapter.adapter_version,
            input_snapshot_hash=hashlib.sha256(self.adapter.adapter_version.encode()).hexdigest(),
            output_summary={
                "catalogStatus": state.status.value,
                "productCount": len(state.products),
                "demoOnly": state.demo_only,
            },
            data_version=state.catalog_version,
        )
        saved = self.repository.save_snapshot(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return ProductCatalogResponse(session_id=session_id, catalog=saved)

    def readiness(self) -> dict[str, bool]:
        return {
            "product_catalog_repository": self.repository.is_ready(),
            "product_catalog_adapter": self.adapter.is_ready(),
        }
