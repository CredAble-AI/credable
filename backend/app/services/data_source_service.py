import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from app.adapters.data_source_adapter import DataSourceAdapter
from app.repositories.data_source_repository import DataSourceRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.consent import ConsentSourceType, ConsentState, ConsentStatus
from app.schemas.data_source import (
    AdapterRetrievalResult,
    DataSourceListResponse,
    DataSourceState,
    RetrievalStatus,
    VerificationStatus,
)
from app.services.consent_service import ConsentService
from app.services.session_service import CustomerSessionService


class SnapshotMaterializer(Protocol):
    def materialize_if_version_matches(
        self,
        session_id: str,
        data_version: str | None,
    ) -> bool: ...


class DataSourceService:
    def __init__(
        self,
        repository: DataSourceRepository,
        consent_service: ConsentService,
        session_service: CustomerSessionService,
        adapter: DataSourceAdapter,
        bank_internal_materializers: tuple[SnapshotMaterializer, ...] = (),
        credit_information_materializers: tuple[SnapshotMaterializer, ...] = (),
    ) -> None:
        self.repository = repository
        self.consent_service = consent_service
        self.session_service = session_service
        self.adapter = adapter
        self.bank_internal_materializers = bank_internal_materializers
        self.credit_information_materializers = credit_information_materializers

    def initialize(self) -> None:
        self.repository.initialize()

    def list_states(self, session_id: str) -> DataSourceListResponse:
        consent_response = self.consent_service.list_consents(session_id)
        stored = {item.source_type: item for item in self.repository.list_states(session_id)}
        states = [
            self._visible_state(consent, stored.get(consent.source_type))
            for consent in consent_response.consents
        ]
        return DataSourceListResponse(session_id=session_id, data_sources=states)

    def refresh(self, session_id: str, request_id: str) -> DataSourceListResponse:
        session = self.session_service.get_session(session_id).session
        consent_response = self.consent_service.list_consents(session_id)
        states: list[DataSourceState] = []
        for consent in consent_response.consents:
            if consent.status != ConsentStatus.GRANTED:
                states.append(self._consent_required_state(consent))
                continue

            retrieved_at = datetime.now(UTC)
            try:
                result = self.adapter.retrieve(
                    session_id=session_id,
                    demo_profile_id=session.demo_profile.demo_profile_id,
                    source_type=consent.source_type,
                )
            except Exception:
                result = AdapterRetrievalResult(
                    retrieval_status=RetrievalStatus.FAILED,
                    reason_code="DATA_SOURCE_ADAPTER_ERROR",
                )
            materializers = {
                ConsentSourceType.BANK_INTERNAL: self.bank_internal_materializers,
                ConsentSourceType.CREDIT_INFORMATION: self.credit_information_materializers,
            }.get(consent.source_type, ())
            materialization_error_code = {
                ConsentSourceType.BANK_INTERNAL: "BANK_DATA_MATERIALIZATION_ERROR",
                ConsentSourceType.CREDIT_INFORMATION: "CREDIT_INFORMATION_MATERIALIZATION_ERROR",
            }.get(consent.source_type, "DATA_MATERIALIZATION_ERROR")
            if (
                materializers
                and result.retrieval_status == RetrievalStatus.RETRIEVED
                and result.verification_status == VerificationStatus.VERIFIED
            ):
                try:
                    for materializer in materializers:
                        materializer.materialize_if_version_matches(
                            session_id,
                            result.data_version,
                        )
                except Exception:
                    result = AdapterRetrievalResult(
                        retrieval_status=RetrievalStatus.FAILED,
                        reason_code=materialization_error_code,
                    )
            state = DataSourceState(
                source_type=consent.source_type,
                display_name=consent.display_name,
                retrieval_status=result.retrieval_status,
                verification_status=result.verification_status,
                observed_at=result.observed_at,
                retrieved_at=retrieved_at,
                data_version=result.data_version,
                reason_code=result.reason_code,
            )
            states.append(
                self.repository.save_state(
                    session_id=session_id,
                    state=state,
                    audit_event=self._audit_event(
                        session_id=session_id,
                        consent=consent,
                        state=state,
                        demo_profile_id=session.demo_profile.demo_profile_id,
                        profile_data_version=session.data_version,
                        request_id=request_id,
                    ),
                )
            )
        return DataSourceListResponse(session_id=session_id, data_sources=states)

    def _visible_state(
        self,
        consent: ConsentState,
        stored: DataSourceState | None,
    ) -> DataSourceState:
        if consent.status != ConsentStatus.GRANTED:
            return self._consent_required_state(consent)
        if stored is None:
            return self._not_requested_state(consent)
        if (
            consent.granted_at is not None
            and stored.retrieved_at is not None
            and stored.retrieved_at < consent.granted_at
        ):
            return self._not_requested_state(consent)
        return stored

    def _consent_required_state(self, consent: ConsentState) -> DataSourceState:
        return DataSourceState(
            source_type=consent.source_type,
            display_name=consent.display_name,
            retrieval_status=RetrievalStatus.CONSENT_REQUIRED,
            verification_status=VerificationStatus.NOT_STARTED,
            reason_code="CONSENT_REQUIRED",
        )

    def _not_requested_state(self, consent: ConsentState) -> DataSourceState:
        return DataSourceState(
            source_type=consent.source_type,
            display_name=consent.display_name,
            retrieval_status=RetrievalStatus.NOT_REQUESTED,
            verification_status=VerificationStatus.NOT_STARTED,
        )

    def _audit_event(
        self,
        *,
        session_id: str,
        consent: ConsentState,
        state: DataSourceState,
        demo_profile_id: str,
        profile_data_version: str,
        request_id: str,
    ) -> SessionAuditEvent:
        snapshot = {
            "sourceType": consent.source_type.value,
            "consentStatus": consent.status.value,
            "consentScopeVersion": consent.scope_version,
            "demoProfileId": demo_profile_id,
            "profileDataVersion": profile_data_version,
        }
        snapshot_json = json.dumps(snapshot, separators=(",", ":"), sort_keys=True)
        return SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.DATA_SOURCE_REFRESHED,
            timestamp=state.retrieved_at,
            actor=AuditActor.SYSTEM,
            input_version=consent.scope_version,
            input_snapshot_hash=hashlib.sha256(snapshot_json.encode()).hexdigest(),
            output_summary={
                "sourceType": state.source_type.value,
                "retrievalStatus": state.retrieval_status.value,
                "verificationStatus": state.verification_status.value,
                "demoOnly": state.demo_only,
            },
            data_version=state.data_version,
        )

    def readiness(self) -> dict[str, bool]:
        return {
            "data_source_repository": self.repository.is_ready(),
            "data_source_adapter": self.adapter.is_ready(),
        }
