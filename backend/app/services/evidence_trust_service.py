import base64
import binascii
import hashlib
import hmac
import json
from pathlib import Path
from typing import Protocol

from app.schemas.evidence_file import DemoEvidenceFileDefinition
from app.schemas.evidence_trust import (
    DemoEvidenceTrustKey,
    DemoEvidenceTrustKeyCatalogData,
    EvidenceTrustChannel,
    EvidenceTrustStatus,
    EvidenceTrustVerification,
    EvidenceVerifiedScope,
)


class EvidenceTrustVerifier(Protocol):
    def verify(
        self, definition: DemoEvidenceFileDefinition | None
    ) -> EvidenceTrustVerification: ...

    def is_ready(self) -> bool: ...


class DemoEvidenceDefinitionProvider(Protocol):
    def list_all(self) -> list[DemoEvidenceFileDefinition]: ...


class DemoEvidenceTrustKeyCatalog:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._catalog: DemoEvidenceTrustKeyCatalogData | None = None
        self._keys: dict[str, DemoEvidenceTrustKey] = {}

    def get(self, key_id: str) -> DemoEvidenceTrustKey | None:
        self._load()
        return self._keys.get(key_id)

    def is_ready(self) -> bool:
        try:
            self._load()
        except (OSError, ValueError):
            return False
        return True

    def _load(self) -> DemoEvidenceTrustKeyCatalogData:
        if self._catalog is None:
            self._catalog = DemoEvidenceTrustKeyCatalogData.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
            self._keys = {item.key_id: item for item in self._catalog.keys}
        return self._catalog


def canonical_manifest_payload(definition: DemoEvidenceFileDefinition) -> bytes:
    payload = {
        "dataVersion": definition.data_version,
        "demoFileId": definition.demo_file_id,
        "documentSha256": definition.trusted_sha256 or definition.sha256,
        "evidenceType": definition.evidence_type,
        "manifest": definition.manifest.model_dump(mode="json", by_alias=True),
        "observedAt": definition.observed_at.isoformat(),
        "qualityPolicyVersion": definition.quality_policy_version,
        "qualityReferenceAt": definition.quality_reference_at.isoformat(),
        "requiredManifestFields": definition.required_manifest_fields,
        "sourceType": definition.source_type.value,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


class DemoSignedManifestVerifier:
    _SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")

    def __init__(
        self,
        key_catalog: DemoEvidenceTrustKeyCatalog,
        definition_provider: DemoEvidenceDefinitionProvider,
    ) -> None:
        self.key_catalog = key_catalog
        self.definition_provider = definition_provider

    def verify(self, definition: DemoEvidenceFileDefinition | None) -> EvidenceTrustVerification:
        if definition is None or definition.manifest_signature is None:
            return self._not_verified("DEMO_MANIFEST_SIGNATURE_MISSING")
        signature = definition.manifest_signature
        key = self.key_catalog.get(signature.key_id)
        if key is None or key.algorithm != signature.algorithm:
            return self._not_verified(
                "DEMO_MANIFEST_SIGNING_KEY_NOT_FOUND",
                algorithm=signature.algorithm,
                key_id=signature.key_id,
            )
        try:
            signature_bytes = base64.b64decode(signature.value, validate=True)
        except (binascii.Error, ValueError):
            return self._not_verified(
                "DEMO_MANIFEST_SIGNATURE_INVALID",
                algorithm=signature.algorithm,
                key_id=signature.key_id,
            )
        verified = self._verify_rs256(
            canonical_manifest_payload(definition),
            signature_bytes,
            key,
        )
        if not verified:
            return self._not_verified(
                "DEMO_MANIFEST_SIGNATURE_INVALID",
                algorithm=signature.algorithm,
                key_id=signature.key_id,
            )
        return EvidenceTrustVerification(
            status=EvidenceTrustStatus.VERIFIED,
            channel=EvidenceTrustChannel.SERVER_SIGNED_MANIFEST,
            verified_scopes=[
                EvidenceVerifiedScope.DOCUMENT_INTEGRITY,
                EvidenceVerifiedScope.MANIFEST_BINDING,
                EvidenceVerifiedScope.DEMO_ISSUER_IDENTITY,
            ],
            algorithm=signature.algorithm,
            key_id=signature.key_id,
            rationale_code="DEMO_SIGNED_MANIFEST_VERIFIED",
        )

    def _verify_rs256(
        self,
        payload: bytes,
        signature: bytes,
        key: DemoEvidenceTrustKey,
    ) -> bool:
        modulus = int(key.modulus_hex, 16)
        encoded_length = (modulus.bit_length() + 7) // 8
        if len(signature) != encoded_length:
            return False
        recovered = pow(int.from_bytes(signature), key.public_exponent, modulus).to_bytes(
            encoded_length
        )
        digest_info = self._SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(payload).digest()
        padding_length = encoded_length - len(digest_info) - 3
        if padding_length < 8:
            return False
        expected = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info
        return hmac.compare_digest(recovered, expected)

    def _not_verified(
        self,
        rationale_code: str,
        *,
        algorithm: str | None = None,
        key_id: str | None = None,
    ) -> EvidenceTrustVerification:
        return EvidenceTrustVerification(
            status=EvidenceTrustStatus.NOT_VERIFIED,
            channel=EvidenceTrustChannel.UNVERIFIED_DOCUMENT,
            algorithm=algorithm,
            key_id=key_id,
            rationale_code=rationale_code,
        )

    def is_ready(self) -> bool:
        if not self.key_catalog.is_ready():
            return False
        try:
            definitions = self.definition_provider.list_all()
            return bool(definitions) and all(
                self.verify(item).status == EvidenceTrustStatus.VERIFIED for item in definitions
            )
        except (OSError, ValueError):
            return False
