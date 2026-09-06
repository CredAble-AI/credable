import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import ApiDomainError, ResourceConflictError, ResourceNotFoundError
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.evidence_consent import EvidenceConsentState
from app.schemas.evidence_file import (
    DemoEvidenceFileCatalogData,
    DemoEvidenceFileDefinition,
    DemoEvidenceFileDescriptor,
    EvidenceCollectionMode,
    EvidenceSubmissionOptionResponse,
    EvidenceSubmissionRequirement,
    EvidenceSubmissionRequirementStatus,
    UploadedEvidenceFile,
)
from app.schemas.evidence_selection import EvidenceSelectionState, EvidenceSelectionStatus
from app.schemas.evidence_submission import (
    DemoEvidenceSubmissionCatalogData,
    DemoEvidenceSubmissionDefinition,
    EvidenceSubmissionCreateRequest,
    EvidenceSubmissionMode,
    EvidenceSubmissionResponse,
    EvidenceSubmissionState,
    EvidenceSubmissionStatus,
)
from app.services.evidence_consent_service import EvidenceConsentService
from app.services.evidence_selection_service import EvidenceSelectionService
from app.services.session_service import CustomerSessionService


class DemoEvidenceSubmissionCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoEvidenceSubmissionCatalogData | None = None
        self._submissions: dict[str, DemoEvidenceSubmissionDefinition] = {}

    def get(self, evidence_type: str) -> DemoEvidenceSubmissionDefinition | None:
        self._load()
        return self._submissions.get(evidence_type)

    def is_ready(self) -> bool:
        try:
            self._load()
        except (OSError, ValueError):
            return False
        return True

    def _load(self) -> DemoEvidenceSubmissionCatalogData:
        if self._catalog is None:
            self._catalog = DemoEvidenceSubmissionCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
            self._submissions = {item.evidence_type: item for item in self._catalog.submissions}
        return self._catalog


class DemoEvidenceFileCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoEvidenceFileCatalogData | None = None
        self._files_by_evidence_type: dict[str, DemoEvidenceFileDefinition] = {}
        self._scenario_files_by_evidence_type: dict[str, list[DemoEvidenceFileDefinition]] = {}
        self._files_by_id: dict[str, DemoEvidenceFileDefinition] = {}

    def get_for_evidence_type(self, evidence_type: str) -> DemoEvidenceFileDefinition | None:
        self._load()
        return self._files_by_evidence_type.get(evidence_type)

    def get_by_id(self, demo_file_id: str) -> DemoEvidenceFileDefinition | None:
        self._load()
        return self._files_by_id.get(demo_file_id)

    def list_for_evidence_type(self, evidence_type: str) -> list[DemoEvidenceFileDefinition]:
        self._load()
        return list(self._scenario_files_by_evidence_type.get(evidence_type, []))

    def get_by_asset_hash(
        self,
        evidence_type: str,
        sha256: str,
    ) -> DemoEvidenceFileDefinition | None:
        return next(
            (item for item in self.list_for_evidence_type(evidence_type) if item.sha256 == sha256),
            None,
        )

    def file_path(self, definition: DemoEvidenceFileDefinition) -> Path:
        catalog_root = self.catalog_path.parent.resolve()
        file_path = (catalog_root / definition.relative_path).resolve()
        if not file_path.is_relative_to(catalog_root):
            raise ValueError("Demo Evidence file path must remain inside the data directory")
        return file_path

    def asset_matches_manifest(self, definition: DemoEvidenceFileDefinition) -> bool:
        try:
            content = self.file_path(definition).read_bytes()
        except OSError:
            return False
        return (
            len(content) == definition.size_bytes
            and hashlib.sha256(content).hexdigest() == definition.sha256
        )

    def is_ready(self) -> bool:
        try:
            catalog = self._load()
        except (OSError, ValueError):
            return False
        return all(self.asset_matches_manifest(item) for item in catalog.files)

    def _load(self) -> DemoEvidenceFileCatalogData:
        if self._catalog is None:
            self._catalog = DemoEvidenceFileCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
            self._scenario_files_by_evidence_type = {}
            self._files_by_evidence_type = {}
            for item in self._catalog.files:
                self._scenario_files_by_evidence_type.setdefault(item.evidence_type, []).append(
                    item
                )
                if item.is_default:
                    self._files_by_evidence_type[item.evidence_type] = item
            self._files_by_id = {item.demo_file_id: item for item in self._catalog.files}
        return self._catalog


class EvidenceSubmissionService:
    def __init__(
        self,
        repository: EvidenceSubmissionRepository,
        session_service: CustomerSessionService,
        selection_service: EvidenceSelectionService,
        evidence_consent_service: EvidenceConsentService,
        catalog: DemoEvidenceSubmissionCatalog,
        file_catalog: DemoEvidenceFileCatalog,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.selection_service = selection_service
        self.evidence_consent_service = evidence_consent_service
        self.catalog = catalog
        self.file_catalog = file_catalog

    def initialize(self) -> None:
        self.repository.initialize()

    def get_latest(self, session_id: str) -> EvidenceSubmissionResponse:
        self.session_service.get_session(session_id)
        return EvidenceSubmissionResponse(
            session_id=session_id,
            submission=self.repository.get_latest(session_id),
        )

    def get_submission_option(
        self,
        session_id: str,
        selection_id: str,
    ) -> EvidenceSubmissionOptionResponse:
        selection = self._require_current_selection(session_id, selection_id)
        selected = selection.selected_evidence
        if selected is None:
            raise ResourceConflictError(
                code="EVIDENCE_NOT_SELECTED",
                message="제출할 Evidence가 선택되지 않았습니다.",
            )

        definition = self.file_catalog.get_for_evidence_type(selected.evidence_type)
        collection_mode = selected.collection_mode or (
            definition.collection_mode
            if definition is not None
            else EvidenceCollectionMode.UNAVAILABLE
        )
        if collection_mode == EvidenceCollectionMode.DEMO_FILE_UPLOAD and (
            definition is None or not self.file_catalog.asset_matches_manifest(definition)
        ):
            collection_mode = EvidenceCollectionMode.UNAVAILABLE

        requirement_status = EvidenceSubmissionRequirementStatus.UNAVAILABLE
        reason_code = "EVIDENCE_COLLECTION_UNAVAILABLE"
        if collection_mode != EvidenceCollectionMode.UNAVAILABLE:
            consent_granted = self.evidence_consent_service.is_currently_granted(
                session_id,
                selection_id,
            )
            if consent_granted:
                requirement_status = EvidenceSubmissionRequirementStatus.READY
                reason_code = None
            else:
                requirement_status = EvidenceSubmissionRequirementStatus.CONSENT_REQUIRED
                reason_code = "EVIDENCE_SELECTION_CONSENT_REQUIRED"

        demo_file = None
        demo_files: list[DemoEvidenceFileDescriptor] = []
        upload_policy = None
        if collection_mode == EvidenceCollectionMode.DEMO_FILE_UPLOAD and definition is not None:
            scenario_definitions = self.file_catalog.list_for_evidence_type(selected.evidence_type)
            demo_files = [
                self._file_descriptor(session_id, selection_id, item)
                for item in scenario_definitions
                if self.file_catalog.asset_matches_manifest(item)
            ]
            default_descriptor = next(
                item for item in demo_files if item.demo_file_id == definition.demo_file_id
            )
            demo_file = default_descriptor.model_copy(
                update={
                    "download_url": (
                        f"/v1/sessions/{session_id}/evidence/selections/"
                        f"{selection_id}/demo-file/download"
                    )
                }
            )
            upload_policy = definition.upload_policy

        return EvidenceSubmissionOptionResponse(
            session_id=session_id,
            selection_id=selection_id,
            evidence_type=selected.evidence_type,
            collection_mode=collection_mode,
            submission_requirement=EvidenceSubmissionRequirement(
                status=requirement_status,
                reason_code=reason_code,
                consent_source_type=selected.source_type,
            ),
            demo_file=demo_file,
            demo_files=demo_files,
            upload_policy=upload_policy,
        )

    def _file_descriptor(
        self,
        session_id: str,
        selection_id: str,
        definition: DemoEvidenceFileDefinition,
    ) -> DemoEvidenceFileDescriptor:
        return DemoEvidenceFileDescriptor(
            demo_file_id=definition.demo_file_id,
            display_name=definition.display_name,
            description=definition.description,
            file_name=definition.file_name,
            content_type=definition.content_type,
            size_bytes=definition.size_bytes,
            download_url=(
                f"/v1/sessions/{session_id}/evidence/selections/{selection_id}/"
                f"demo-files/{definition.demo_file_id}/download"
            ),
            scenario_code=definition.scenario_code,
            expected_quality_status=definition.expected_quality_status,
        )

    def get_demo_file(
        self,
        session_id: str,
        selection_id: str,
        demo_file_id: str | None = None,
    ) -> tuple[Path, DemoEvidenceFileDefinition]:
        selection = self._require_current_selection(session_id, selection_id)
        definition = self._require_demo_file_definition(selection)
        if demo_file_id is not None:
            requested = self.file_catalog.get_by_id(demo_file_id)
            if (
                requested is None
                or selection.selected_evidence is None
                or requested.evidence_type != selection.selected_evidence.evidence_type
            ):
                raise ResourceNotFoundError(
                    code="DEMO_EVIDENCE_FILE_NOT_FOUND",
                    message="현재 Evidence 선택에 사용할 Demo 파일을 찾을 수 없습니다.",
                )
            definition = requested
        self._require_consent(session_id, selection_id)
        if not self.file_catalog.asset_matches_manifest(definition):
            raise ResourceConflictError(
                code="DEMO_EVIDENCE_FILE_NOT_CONFIGURED",
                message="선택된 Evidence의 Demo 파일 구성이 유효하지 않습니다.",
            )
        return self.file_catalog.file_path(definition), definition

    def upload_limit(self, session_id: str, selection_id: str) -> int:
        selection = self._require_current_selection(session_id, selection_id)
        definition = self._require_demo_file_definition(selection)
        self._require_consent(session_id, selection_id)
        return definition.upload_policy.max_size_bytes

    def submit_demo_file(
        self,
        *,
        session_id: str,
        selection_id: str,
        file_name: str | None,
        content_type: str | None,
        content: bytes,
        request_id: str,
    ) -> EvidenceSubmissionResponse:
        selection = self._require_current_selection(session_id, selection_id)
        definition = self._require_demo_file_definition(selection)
        consent = self._require_consent(session_id, selection_id)
        self._validate_uploaded_file(
            definition=definition,
            file_name=file_name,
            content_type=content_type,
            content=content,
        )
        uploaded_sha256 = hashlib.sha256(content).hexdigest()
        matched_definition = self.file_catalog.get_by_asset_hash(
            definition.evidence_type,
            uploaded_sha256,
        )
        submitted_definition = matched_definition or definition
        existing = self.repository.get_by_selection_id(selection_id)
        if existing is not None:
            if (
                existing.submission_mode == EvidenceSubmissionMode.DEMO_FILE_UPLOAD
                and existing.uploaded_file is not None
                and existing.uploaded_file.sha256 == uploaded_sha256
            ):
                return EvidenceSubmissionResponse(session_id=session_id, submission=existing)
            raise ResourceConflictError(
                code="EVIDENCE_ALREADY_SUBMITTED",
                message="같은 Evidence 선택에 다른 제출 자료가 이미 등록되어 있습니다.",
            )
        uploaded_file = UploadedEvidenceFile(
            demo_file_id=submitted_definition.demo_file_id,
            file_name=file_name or "",
            content_type=definition.content_type,
            size_bytes=len(content),
            sha256=uploaded_sha256,
        )
        return self._save_submission(
            session_id=session_id,
            selection=selection,
            submission_mode=EvidenceSubmissionMode.DEMO_FILE_UPLOAD,
            definition=self.catalog.get(definition.evidence_type),
            file_definition=submitted_definition,
            request_id=request_id,
            uploaded_file=uploaded_file,
            evidence_consent=consent,
        )

    def submit_demo(
        self,
        session_id: str,
        payload: EvidenceSubmissionCreateRequest,
        request_id: str,
    ) -> EvidenceSubmissionResponse:
        self.session_service.get_session(session_id)
        selection = self.selection_service.get_latest(session_id).selection
        if selection is None or selection.selection_id != payload.selection_id:
            raise ResourceConflictError(
                code="EVIDENCE_SELECTION_NOT_READY",
                message="현재 세션의 최신 Evidence 선택 결과가 필요합니다.",
            )
        if (
            selection.status != EvidenceSelectionStatus.SELECTED
            or selection.selected_evidence is None
        ):
            raise ResourceConflictError(
                code="EVIDENCE_NOT_SELECTED",
                message="제출할 Evidence가 선택되지 않았습니다.",
            )

        existing = self.repository.get_by_selection_id(selection.selection_id)
        if existing is not None:
            return EvidenceSubmissionResponse(session_id=session_id, submission=existing)

        definition = self.catalog.get(selection.selected_evidence.evidence_type)
        return self._save_submission(
            session_id=session_id,
            selection=selection,
            submission_mode=payload.submission_mode,
            definition=definition,
            file_definition=None,
            request_id=request_id,
            uploaded_file=None,
            evidence_consent=None,
        )

    def _save_submission(
        self,
        *,
        session_id: str,
        selection: EvidenceSelectionState,
        submission_mode: EvidenceSubmissionMode,
        definition: DemoEvidenceSubmissionDefinition | None,
        file_definition: DemoEvidenceFileDefinition | None,
        request_id: str,
        uploaded_file: UploadedEvidenceFile | None,
        evidence_consent: EvidenceConsentState | None,
    ) -> EvidenceSubmissionResponse:
        if definition is None or selection.selected_evidence is None:
            raise ResourceConflictError(
                code="DEMO_EVIDENCE_SUBMISSION_NOT_CONFIGURED",
                message="선택된 Evidence의 Demo 제출 자료가 구성되지 않았습니다.",
            )

        submitted_at = datetime.now(UTC)
        observed_at = (
            file_definition.observed_at if file_definition is not None else definition.observed_at
        )
        data_version = (
            file_definition.data_version if file_definition is not None else definition.data_version
        )
        snapshot: dict[str, object] = {
            "selectionId": selection.selection_id,
            "evidenceType": selection.selected_evidence.evidence_type,
            "sourceType": selection.selected_evidence.source_type.value,
            "submissionMode": submission_mode.value,
            "observedAt": observed_at.isoformat(),
            "dataVersion": data_version,
        }
        if uploaded_file is not None:
            snapshot["uploadedFile"] = uploaded_file.model_dump(mode="json", by_alias=True)
            if evidence_consent is None:
                raise ValueError("file upload requires selection-scoped Evidence consent")
            snapshot["evidenceConsentId"] = evidence_consent.evidence_consent_id
            snapshot["consentScopeVersion"] = evidence_consent.scope_version
        else:
            snapshot["sourceReference"] = definition.source_reference
        serialized = json.dumps(
            snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_hash = hashlib.sha256(serialized.encode()).hexdigest()
        state = EvidenceSubmissionState(
            submission_id=f"evd_{uuid4().hex}",
            selection_id=selection.selection_id,
            evidence_type=selection.selected_evidence.evidence_type,
            source_type=selection.selected_evidence.source_type,
            submission_mode=submission_mode,
            status=EvidenceSubmissionStatus.RECEIVED,
            submitted_at=submitted_at,
            observed_at=observed_at,
            submission_snapshot_hash=snapshot_hash,
            data_version=data_version,
            uploaded_file=uploaded_file,
            evidence_consent_id=(
                evidence_consent.evidence_consent_id if evidence_consent is not None else None
            ),
            consent_scope_version=(
                evidence_consent.scope_version if evidence_consent is not None else None
            ),
        )
        output_summary: dict[str, str | bool | int | float] = {
            "submissionStatus": state.status.value,
            "evidenceType": state.evidence_type,
            "sourceType": state.source_type.value,
            "submissionMode": state.submission_mode.value,
            "demoOnly": state.demo_only,
        }
        if uploaded_file is not None:
            output_summary["demoFileId"] = uploaded_file.demo_file_id
            output_summary["uploadedFileSha256"] = uploaded_file.sha256
            output_summary["evidenceConsentId"] = state.evidence_consent_id or "missing"
            output_summary["consentScopeVersion"] = state.consent_scope_version or "missing"
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.EVIDENCE_SUBMITTED,
            timestamp=submitted_at,
            actor=AuditActor.SYSTEM,
            input_version=selection.selection_id,
            input_snapshot_hash=snapshot_hash,
            output_summary=output_summary,
            data_version=state.data_version,
            policy_version=selection.selection_policy_version,
        )
        saved = self.repository.save_submission(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return EvidenceSubmissionResponse(session_id=session_id, submission=saved)

    def _require_current_selection(
        self,
        session_id: str,
        selection_id: str,
    ) -> EvidenceSelectionState:
        self.session_service.get_session(session_id)
        selection = self.selection_service.repository.get_for_session(session_id, selection_id)
        if selection is None:
            raise ResourceNotFoundError(
                code="EVIDENCE_SELECTION_NOT_FOUND",
                message="Evidence 선택 결과를 찾을 수 없습니다.",
            )
        latest = self.selection_service.repository.get_latest(session_id)
        if (
            latest is None
            or latest.selection_id != selection_id
            or selection.status != EvidenceSelectionStatus.SELECTED
            or selection.selected_evidence is None
        ):
            raise ResourceConflictError(
                code="EVIDENCE_NOT_SELECTED",
                message="현재 제출 가능한 Evidence 선택 상태가 아닙니다.",
            )
        return selection

    def _require_demo_file_definition(
        self,
        selection: EvidenceSelectionState,
    ) -> DemoEvidenceFileDefinition:
        selected = selection.selected_evidence
        if selected is None:
            raise ResourceConflictError(
                code="EVIDENCE_NOT_SELECTED",
                message="제출할 Evidence가 선택되지 않았습니다.",
            )
        if selected.collection_mode not in (None, EvidenceCollectionMode.DEMO_FILE_UPLOAD):
            raise ResourceConflictError(
                code="EVIDENCE_COLLECTION_MODE_UNSUPPORTED",
                message="선택된 Evidence는 Demo 파일 업로드 방식이 아닙니다.",
            )
        definition = self.file_catalog.get_for_evidence_type(selected.evidence_type)
        if definition is None:
            raise ResourceConflictError(
                code="DEMO_EVIDENCE_FILE_NOT_CONFIGURED",
                message="선택된 Evidence의 Demo 파일이 구성되지 않았습니다.",
            )
        return definition

    def _require_consent(
        self,
        session_id: str,
        selection_id: str,
    ) -> EvidenceConsentState:
        return self.evidence_consent_service.require_granted(
            session_id,
            selection_id,
        )

    def _validate_uploaded_file(
        self,
        *,
        definition: DemoEvidenceFileDefinition,
        file_name: str | None,
        content_type: str | None,
        content: bytes,
    ) -> None:
        policy = definition.upload_policy
        extension = Path(file_name or "").suffix.lower()
        if content_type not in policy.allowed_content_types or extension not in (
            policy.allowed_extensions
        ):
            raise ApiDomainError(
                code="EVIDENCE_FILE_TYPE_UNSUPPORTED",
                message="PDF 파일만 제출할 수 있습니다.",
                status_code=415,
            )
        if len(content) > policy.max_size_bytes:
            raise ApiDomainError(
                code="EVIDENCE_FILE_TOO_LARGE",
                message="Evidence 파일이 허용된 최대 크기를 초과했습니다.",
                status_code=413,
            )
        if not content.startswith(b"%PDF-"):
            raise ApiDomainError(
                code="EVIDENCE_FILE_CONTENT_INVALID",
                message="유효한 PDF 파일 내용을 확인할 수 없습니다.",
                status_code=422,
            )
        if not self.file_catalog.asset_matches_manifest(definition):
            raise ResourceConflictError(
                code="DEMO_EVIDENCE_FILE_NOT_CONFIGURED",
                message="선택된 Evidence의 Demo 파일 구성이 유효하지 않습니다.",
            )

    def readiness(self) -> dict[str, bool]:
        return {
            "evidence_submission_repository": self.repository.is_ready(),
            "evidence_submission_catalog": self.catalog.is_ready(),
            "demo_evidence_file_catalog": self.file_catalog.is_ready(),
        }
