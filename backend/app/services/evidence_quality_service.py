import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import EvidenceSubmissionNotFoundError, ResourceConflictError
from app.repositories.evidence_consent_repository import EvidenceConsentRepository
from app.repositories.evidence_quality_repository import EvidenceQualityRepository
from app.repositories.evidence_submission_repository import EvidenceSubmissionRepository
from app.schemas.audit import AuditActor, AuditStage, SessionAuditEvent
from app.schemas.consent import ConsentStatus
from app.schemas.evidence_file import DemoEvidenceFileDefinition
from app.schemas.evidence_quality import (
    DemoEvidenceQualityCatalogData,
    DemoEvidenceQualityDefinition,
    EvidenceQualityDimension,
    EvidenceQualityDimensionResult,
    EvidenceQualityDimensionStatus,
    EvidenceQualityResponse,
    EvidenceQualityState,
    EvidenceQualityStatus,
)
from app.schemas.evidence_submission import EvidenceSubmissionMode, EvidenceSubmissionState
from app.services.evidence_submission_service import DemoEvidenceFileCatalog
from app.services.session_service import CustomerSessionService


class DemoEvidenceQualityCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoEvidenceQualityCatalogData | None = None
        self._results: dict[str, DemoEvidenceQualityDefinition] = {}

    @property
    def quality_policy_version(self) -> str:
        return self._load().quality_policy_version

    def get(self, evidence_type: str) -> DemoEvidenceQualityDefinition | None:
        self._load()
        return self._results.get(evidence_type)

    def is_ready(self) -> bool:
        try:
            self._load()
        except (OSError, ValueError):
            return False
        return True

    def _load(self) -> DemoEvidenceQualityCatalogData:
        if self._catalog is None:
            self._catalog = DemoEvidenceQualityCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
            self._results = {item.evidence_type: item for item in self._catalog.results}
        return self._catalog


class EvidenceQualityService:
    def __init__(
        self,
        repository: EvidenceQualityRepository,
        submission_repository: EvidenceSubmissionRepository,
        evidence_consent_repository: EvidenceConsentRepository,
        session_service: CustomerSessionService,
        catalog: DemoEvidenceQualityCatalog,
        file_catalog: DemoEvidenceFileCatalog,
    ) -> None:
        self.repository = repository
        self.submission_repository = submission_repository
        self.evidence_consent_repository = evidence_consent_repository
        self.session_service = session_service
        self.catalog = catalog
        self.file_catalog = file_catalog

    def initialize(self) -> None:
        self.repository.initialize()

    def get(
        self,
        session_id: str,
        submission_id: str,
    ) -> EvidenceQualityResponse:
        submission = self._submission(session_id, submission_id)
        return EvidenceQualityResponse(
            session_id=session_id,
            quality=self.repository.get_for_submission(session_id, submission.submission_id),
        )

    def check(
        self,
        session_id: str,
        submission_id: str,
        request_id: str,
    ) -> EvidenceQualityResponse:
        submission = self._submission(session_id, submission_id)
        existing = self.repository.get_for_submission(session_id, submission_id)
        if existing is not None:
            return EvidenceQualityResponse(session_id=session_id, quality=existing)

        if submission.submission_mode == EvidenceSubmissionMode.DEMO_FILE_UPLOAD:
            self._require_active_submission_consent(session_id, submission)
            checks, quality_policy_version = self._binary_file_checks(submission)
        else:
            definition = self.catalog.get(submission.evidence_type)
            checks = (
                definition.checks
                if definition is not None
                else [
                    EvidenceQualityDimensionResult(
                        dimension=dimension,
                        status=EvidenceQualityDimensionStatus.NOT_VERIFIED,
                        rationale_code=f"DEMO_{dimension.value}_POLICY_NOT_CONFIGURED",
                    )
                    for dimension in EvidenceQualityDimension
                ]
            )
            quality_policy_version = self.catalog.quality_policy_version
        rejection_codes = [
            item.rationale_code
            for item in checks
            if item.status != EvidenceQualityDimensionStatus.PASSED
        ]
        status = (
            EvidenceQualityStatus.REJECTED if rejection_codes else EvidenceQualityStatus.ACCEPTED
        )
        checked_at = datetime.now(UTC)
        state = EvidenceQualityState(
            quality_check_id=f"evq_{uuid4().hex}",
            submission_id=submission.submission_id,
            evidence_type=submission.evidence_type,
            status=status,
            checks=checks,
            rejection_codes=rejection_codes,
            eligible_for_reassessment=status == EvidenceQualityStatus.ACCEPTED,
            checked_at=checked_at,
            submission_snapshot_hash=submission.submission_snapshot_hash,
            data_version=submission.data_version,
            quality_policy_version=quality_policy_version,
        )
        audit_event = SessionAuditEvent(
            event_id=f"evt_{uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            stage=AuditStage.EVIDENCE_QUALITY_CHECKED,
            timestamp=checked_at,
            actor=AuditActor.SYSTEM,
            input_version=submission.submission_id,
            input_snapshot_hash=submission.submission_snapshot_hash,
            output_summary={
                "qualityStatus": state.status.value,
                "failedCheckCount": len(rejection_codes),
                "eligibleForReassessment": state.eligible_for_reassessment,
                "evidenceType": state.evidence_type,
                "demoOnly": state.demo_only,
            },
            data_version=state.data_version,
            policy_version=state.quality_policy_version,
        )
        saved = self.repository.save_quality(
            session_id=session_id,
            state=state,
            audit_event=audit_event,
        )
        return EvidenceQualityResponse(session_id=session_id, quality=saved)

    def _require_active_submission_consent(
        self,
        session_id: str,
        submission: EvidenceSubmissionState,
    ) -> None:
        consent = self.evidence_consent_repository.get_for_selection(
            session_id,
            submission.selection_id,
        )
        if (
            consent is None
            or consent.status != ConsentStatus.GRANTED
            or consent.selection_id != submission.selection_id
            or consent.evidence_type != submission.evidence_type
            or consent.source_type != submission.source_type
            or submission.evidence_consent_id is None
            or consent.evidence_consent_id != submission.evidence_consent_id
            or submission.consent_scope_version is None
            or consent.scope_version != submission.consent_scope_version
        ):
            raise ResourceConflictError(
                code="EVIDENCE_CONSENT_NOT_ACTIVE",
                message="현재 유효한 Evidence 동의가 있는 자료만 품질 검증할 수 있습니다.",
            )

    def _submission(
        self,
        session_id: str,
        submission_id: str,
    ) -> EvidenceSubmissionState:
        self.session_service.get_session(session_id)
        submission = self.submission_repository.get_for_session(session_id, submission_id)
        if submission is None:
            raise EvidenceSubmissionNotFoundError(submission_id)
        return submission

    def _binary_file_checks(
        self,
        submission: EvidenceSubmissionState,
    ) -> tuple[list[EvidenceQualityDimensionResult], str]:
        uploaded = submission.uploaded_file
        definition = self.file_catalog.get_by_id(uploaded.demo_file_id) if uploaded else None
        policy_version = (
            definition.quality_policy_version
            if definition is not None
            else "demo-binary-evidence-quality-policy-v1"
        )
        provenance_valid = (
            uploaded is not None
            and definition is not None
            and definition.evidence_type == submission.evidence_type
            and definition.source_type == submission.source_type
            and definition.data_version == submission.data_version
            and self._uploaded_submission_snapshot_matches(submission)
        )
        asset_valid = definition is not None and self.file_catalog.asset_matches_manifest(
            definition
        )
        authenticity_valid = (
            provenance_valid
            and asset_valid
            and uploaded is not None
            and definition is not None
            and uploaded.sha256 == definition.sha256
        )
        manifest = definition.manifest if definition is not None else None
        manifest_data = (
            manifest.model_dump(mode="json", by_alias=True) if manifest is not None else {}
        )
        completeness_valid = definition is not None and all(
            manifest_data.get(field) not in (None, "", [], {})
            for field in definition.required_manifest_fields
        )
        freshness_valid = (
            definition is not None
            and manifest is not None
            and manifest.period_start is not None
            and manifest.period_end is not None
            and manifest.generated_on is not None
            and manifest.period_start <= manifest.period_end
            and manifest.period_end == definition.observed_at.date()
            and definition.observed_at <= definition.quality_reference_at
            and manifest.generated_on <= definition.quality_reference_at.date()
        )
        consistency_valid = self._manifest_totals_are_consistent(definition)
        manipulation_valid = (
            authenticity_valid
            and uploaded is not None
            and definition is not None
            and uploaded.file_name == definition.file_name
            and uploaded.content_type == definition.content_type
            and uploaded.size_bytes == definition.size_bytes
        )
        results = [
            self._dimension_result(
                EvidenceQualityDimension.PROVENANCE,
                provenance_valid,
                "DEMO_SERVER_DOCUMENT_PROVENANCE_CONFIRMED",
                "DEMO_SERVER_DOCUMENT_PROVENANCE_INVALID",
            ),
            self._dimension_result(
                EvidenceQualityDimension.FRESHNESS,
                freshness_valid,
                "DEMO_MANIFEST_POINT_IN_TIME_VALID",
                "DEMO_MANIFEST_POINT_IN_TIME_INVALID",
            ),
            self._dimension_result(
                EvidenceQualityDimension.AUTHENTICITY,
                authenticity_valid,
                "DEMO_SERVER_FILE_HASH_MATCHED",
                "DEMO_SERVER_FILE_HASH_NOT_VERIFIED",
            ),
            self._dimension_result(
                EvidenceQualityDimension.COMPLETENESS,
                completeness_valid,
                "DEMO_MANIFEST_REQUIRED_FIELDS_PRESENT",
                "DEMO_MANIFEST_REQUIRED_FIELDS_MISSING",
            ),
            self._dimension_result(
                EvidenceQualityDimension.CONSISTENCY,
                consistency_valid,
                "DEMO_MANIFEST_TOTALS_CONSISTENT",
                "DEMO_MANIFEST_TOTALS_INCONSISTENT",
            ),
            self._dimension_result(
                EvidenceQualityDimension.MANIPULATION_RISK,
                manipulation_valid,
                "DEMO_FILE_METADATA_AND_HASH_UNCHANGED",
                "DEMO_FILE_METADATA_OR_HASH_CHANGED",
            ),
        ]
        return results, policy_version

    def _uploaded_submission_snapshot_matches(
        self,
        submission: EvidenceSubmissionState,
    ) -> bool:
        if submission.uploaded_file is None:
            return False
        snapshot = {
            "selectionId": submission.selection_id,
            "evidenceType": submission.evidence_type,
            "sourceType": submission.source_type.value,
            "submissionMode": submission.submission_mode.value,
            "observedAt": submission.observed_at.isoformat(),
            "dataVersion": submission.data_version,
            "uploadedFile": submission.uploaded_file.model_dump(mode="json", by_alias=True),
        }
        if (
            submission.evidence_consent_id is not None
            and submission.consent_scope_version is not None
        ):
            snapshot["evidenceConsentId"] = submission.evidence_consent_id
            snapshot["consentScopeVersion"] = submission.consent_scope_version
        serialized = json.dumps(
            snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode()).hexdigest() == (
            submission.submission_snapshot_hash
        )

    def _manifest_totals_are_consistent(
        self,
        definition: DemoEvidenceFileDefinition | None,
    ) -> bool:
        if definition is None:
            return False
        manifest = definition.manifest
        if not manifest.monthly_summaries or manifest.totals is None:
            return False
        months = [item.month for item in manifest.monthly_summaries]
        if len(months) != len(set(months)):
            return False
        if any(
            item.sales_amount - item.deposit_amount != item.difference_amount
            for item in manifest.monthly_summaries
        ):
            return False
        return (
            sum(item.sales_amount for item in manifest.monthly_summaries)
            == manifest.totals.sales_amount
            and sum(item.deposit_amount for item in manifest.monthly_summaries)
            == manifest.totals.deposit_amount
            and sum(item.difference_amount for item in manifest.monthly_summaries)
            == manifest.totals.difference_amount
            and manifest.totals.sales_amount - manifest.totals.deposit_amount
            == manifest.totals.difference_amount
        )

    def _dimension_result(
        self,
        dimension: EvidenceQualityDimension,
        passed: bool,
        passed_code: str,
        failed_code: str,
    ) -> EvidenceQualityDimensionResult:
        return EvidenceQualityDimensionResult(
            dimension=dimension,
            status=(
                EvidenceQualityDimensionStatus.PASSED
                if passed
                else EvidenceQualityDimensionStatus.FAILED
            ),
            rationale_code=passed_code if passed else failed_code,
        )

    def readiness(self) -> dict[str, bool]:
        return {
            "evidence_quality_repository": self.repository.is_ready(),
            "evidence_quality_catalog": self.catalog.is_ready(),
            "demo_evidence_file_catalog": self.file_catalog.is_ready(),
        }
