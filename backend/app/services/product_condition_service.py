import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.adapters.product_condition_adapter import ProductConditionAdapter
from app.repositories.product_condition_repository import ProductConditionRepository
from app.schemas.assessment import AssessmentState
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.data_source import DataSourceState
from app.schemas.product import BankProduct, ProductCatalogState, ProductCatalogStatus
from app.schemas.product_condition import (
    ProductCondition,
    ProductConditionAdapterInput,
    ProductConditionAdapterResult,
    ProductConditionInputSnapshot,
    ProductConditionQueryResponse,
    ProductConditionQueryState,
    ProductConditionQueryStatus,
    ProductConditionStatus,
)
from app.services.assessment_service import AssessmentService
from app.services.data_source_service import DataSourceService
from app.services.product_catalog_service import ProductCatalogService
from app.services.session_service import CustomerSessionService


class ProductConditionService:
    def __init__(
        self,
        repository: ProductConditionRepository,
        session_service: CustomerSessionService,
        catalog_service: ProductCatalogService,
        assessment_service: AssessmentService,
        data_source_service: DataSourceService,
        adapter: ProductConditionAdapter,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.catalog_service = catalog_service
        self.assessment_service = assessment_service
        self.data_source_service = data_source_service
        self.adapter = adapter

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> ProductConditionQueryResponse:
        self.session_service.get_session(session_id)
        state = self.repository.get_latest(session_id)
        if state is None:
            state = ProductConditionQueryState(status=ProductConditionQueryStatus.NOT_QUERIED)
        return ProductConditionQueryResponse(session_id=session_id, query=state)

    def query(self, session_id: str, request_id: str) -> ProductConditionQueryResponse:
        session = self.session_service.get_session(session_id).session
        catalog = self.catalog_service.get_latest(session_id).catalog
        if catalog.status != ProductCatalogStatus.AVAILABLE:
            return self._save_catalog_unavailable(
                session_id=session_id,
                catalog=catalog,
                request_id=request_id,
            )

        assessment = self.assessment_service.get_latest(session_id).assessment
        data_sources = self.data_source_service.list_states(session_id).data_sources
        data_snapshot_id = self._data_snapshot_id(data_sources)
        if catalog.catalog_snapshot_id is None:
            raise RuntimeError("available catalog must have catalogSnapshotId")
        snapshot = ProductConditionInputSnapshot(
            catalog_snapshot_id=catalog.catalog_snapshot_id,
            demo_profile_id=session.demo_profile.demo_profile_id,
            products=catalog.products,
            assessment=assessment,
            data_sources=data_sources,
            data_snapshot_id=data_snapshot_id,
        )
        snapshot_json, snapshot_hash = self._serialize_and_hash(snapshot)
        del snapshot_json
        queried_at = datetime.now(UTC)
        conditions = [
            self._query_product(
                session_id=session_id,
                demo_profile_id=session.demo_profile.demo_profile_id,
                catalog_snapshot_id=catalog.catalog_snapshot_id,
                product=product,
                assessment=assessment,
                data_sources=data_sources,
                data_snapshot_id=data_snapshot_id,
                queried_at=queried_at,
            )
            for product in catalog.products
        ]
        query_status, reason_code = self._query_status(conditions)
        state = ProductConditionQueryState(
            query_id=f"pcq_{uuid4().hex}",
            status=query_status,
            conditions=conditions,
            queried_at=queried_at,
            catalog_snapshot_id=catalog.catalog_snapshot_id,
            assessment_id=assessment.assessment_id,
            data_snapshot_id=data_snapshot_id,
            reason_code=reason_code,
        )
        return self._save(
            session_id=session_id,
            state=state,
            snapshot=snapshot,
            snapshot_hash=snapshot_hash,
            input_version=catalog.catalog_version or catalog.catalog_snapshot_id,
            request_id=request_id,
        )

    def _save_catalog_unavailable(
        self,
        *,
        session_id: str,
        catalog: ProductCatalogState,
        request_id: str,
    ) -> ProductConditionQueryResponse:
        queried_at = datetime.now(UTC)
        catalog_json, catalog_hash = self._serialize_and_hash(catalog)
        del catalog_json
        state = ProductConditionQueryState(
            query_id=f"pcq_{uuid4().hex}",
            status=ProductConditionQueryStatus.CATALOG_UNAVAILABLE,
            queried_at=queried_at,
            catalog_snapshot_id=catalog.catalog_snapshot_id,
            reason_code=catalog.reason_code
            or {
                ProductCatalogStatus.NOT_LOADED: "PRODUCT_CATALOG_NOT_LOADED",
                ProductCatalogStatus.CATALOG_NOT_CONFIGURED: ("PRODUCT_CATALOG_NOT_CONFIGURED"),
                ProductCatalogStatus.FAILED: "PRODUCT_CATALOG_FAILED",
            }[catalog.status],
        )
        return self._save(
            session_id=session_id,
            state=state,
            snapshot=None,
            snapshot_hash=catalog_hash,
            input_version=catalog.catalog_version
            or catalog.catalog_snapshot_id
            or "PRODUCT_CATALOG_NOT_LOADED",
            request_id=request_id,
        )

    def _query_product(
        self,
        *,
        session_id: str,
        demo_profile_id: str,
        catalog_snapshot_id: str,
        product: BankProduct,
        assessment: AssessmentState,
        data_sources: list[DataSourceState],
        data_snapshot_id: str,
        queried_at: datetime,
    ) -> ProductCondition:
        input_data = ProductConditionAdapterInput(
            session_id=session_id,
            demo_profile_id=demo_profile_id,
            product=product,
            catalog_snapshot_id=catalog_snapshot_id,
            assessment=assessment,
            data_sources=data_sources,
            data_snapshot_id=data_snapshot_id,
        )
        try:
            result = self.adapter.query(input_data)
        except Exception:
            result = ProductConditionAdapterResult(
                status=ProductConditionStatus.QUERY_FAILED,
                reason_code="PRODUCT_CONDITION_ADAPTER_ERROR",
            )
        return ProductCondition(
            product_id=product.product_id,
            status=result.status,
            personalized_max_amount=result.personalized_max_amount,
            personalized_annual_rate_range=result.personalized_annual_rate_range,
            personalized_term_range_months=result.personalized_term_range_months,
            policy_version=result.policy_version,
            queried_at=queried_at,
            reason_code=result.reason_code,
        )

    def _query_status(
        self,
        conditions: list[ProductCondition],
    ) -> tuple[ProductConditionQueryStatus, str | None]:
        failed_count = sum(
            item.status == ProductConditionStatus.QUERY_FAILED for item in conditions
        )
        if failed_count == 0:
            return ProductConditionQueryStatus.COMPLETED, None
        if failed_count == len(conditions):
            return ProductConditionQueryStatus.FAILED, "ALL_PRODUCT_QUERIES_FAILED"
        return ProductConditionQueryStatus.PARTIAL, "SOME_PRODUCT_QUERIES_FAILED"

    def _data_snapshot_id(self, states: list[DataSourceState]) -> str:
        _, digest = self._serialize_and_hash(states)
        return f"dss_{digest}"

    def _serialize_and_hash(self, value) -> tuple[str, str]:
        if hasattr(value, "model_dump"):
            content = value.model_dump(mode="json", by_alias=True)
        else:
            content = [item.model_dump(mode="json", by_alias=True) for item in value]
        serialized = json.dumps(
            content,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return serialized, hashlib.sha256(serialized.encode()).hexdigest()

    def _save(
        self,
        *,
        session_id: str,
        state: ProductConditionQueryState,
        snapshot: ProductConditionInputSnapshot | None,
        snapshot_hash: str,
        input_version: str,
        request_id: str,
    ) -> ProductConditionQueryResponse:
        policy_versions = {item.policy_version for item in state.conditions if item.policy_version}
        failed_count = sum(
            item.status == ProductConditionStatus.QUERY_FAILED for item in state.conditions
        )
        if state.queried_at is None:
            raise ValueError("queried state requires queriedAt")
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.PRODUCT_CONDITIONS_QUERIED,
            timestamp=state.queried_at,
            actor=AuditActor.SYSTEM,
            input_version=input_version,
            input_snapshot_hash=snapshot_hash,
            output_summary={
                "queryStatus": state.status.value,
                "productCount": len(state.conditions),
                "failedCount": failed_count,
                "demoOnly": state.demo_only,
            },
            data_version=state.data_snapshot_id,
            model_version=(snapshot.assessment.model_version if snapshot is not None else None),
            policy_version=(next(iter(policy_versions)) if len(policy_versions) == 1 else None),
        )
        saved = self.repository.save_query(
            session_id=session_id,
            state=state,
            snapshot=snapshot,
            audit_event=audit_event,
        )
        return ProductConditionQueryResponse(session_id=session_id, query=saved)

    def readiness(self) -> dict[str, bool]:
        return {
            "product_condition_repository": self.repository.is_ready(),
            "product_condition_adapter": self.adapter.is_ready(),
        }
