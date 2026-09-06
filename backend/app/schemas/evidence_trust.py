from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class EvidenceTrustChannel(StrEnum):
    SERVER_SIGNED_MANIFEST = "SERVER_SIGNED_MANIFEST"
    BANK_INTERNAL_LEDGER = "BANK_INTERNAL_LEDGER"
    SOURCE_API = "SOURCE_API"
    PDF_DIGITAL_SIGNATURE = "PDF_DIGITAL_SIGNATURE"
    ISSUER_REFERENCE = "ISSUER_REFERENCE"
    UNVERIFIED_DOCUMENT = "UNVERIFIED_DOCUMENT"


class EvidenceTrustStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"


class EvidenceVerifiedScope(StrEnum):
    DOCUMENT_INTEGRITY = "DOCUMENT_INTEGRITY"
    MANIFEST_BINDING = "MANIFEST_BINDING"
    DEMO_ISSUER_IDENTITY = "DEMO_ISSUER_IDENTITY"


class DemoManifestSignature(ApiModel):
    algorithm: Literal["RS256"] = "RS256"
    key_id: str = Field(min_length=1)
    value: str = Field(min_length=1)


class EvidenceTrustVerification(ApiModel):
    status: EvidenceTrustStatus
    channel: EvidenceTrustChannel
    verified_scopes: list[EvidenceVerifiedScope] = Field(default_factory=list)
    algorithm: Literal["RS256"] | None = None
    key_id: str | None = Field(default=None, min_length=1)
    rationale_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_verification(self) -> "EvidenceTrustVerification":
        if self.status == EvidenceTrustStatus.VERIFIED:
            if not self.verified_scopes or self.algorithm is None or self.key_id is None:
                raise ValueError("VERIFIED trust requires scopes, algorithm, and keyId")
        elif self.verified_scopes:
            raise ValueError("NOT_VERIFIED trust cannot expose verified scopes")
        return self


class DemoEvidenceTrustKey(ApiModel):
    key_id: str = Field(min_length=1)
    algorithm: Literal["RS256"] = "RS256"
    modulus_hex: str = Field(pattern=r"^[0-9a-f]+$", min_length=512, max_length=1024)
    public_exponent: int = Field(default=65537, gt=1)


class DemoEvidenceTrustKeyCatalogData(ApiModel):
    data_version: str = Field(min_length=1)
    keys: list[DemoEvidenceTrustKey] = Field(min_length=1)
    demo_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_unique_keys(self) -> "DemoEvidenceTrustKeyCatalogData":
        key_ids = [item.key_id for item in self.keys]
        if len(key_ids) != len(set(key_ids)):
            raise ValueError("Evidence trust keyId values must be unique")
        return self
