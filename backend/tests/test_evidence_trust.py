from app.core.config import settings
from app.schemas.evidence_file import DemoEvidenceFileDefinition
from app.schemas.evidence_trust import DemoManifestSignature, EvidenceTrustStatus
from app.services.evidence_submission_service import DemoEvidenceFileCatalog
from app.services.evidence_trust_service import (
    DemoEvidenceTrustKeyCatalog,
    DemoSignedManifestVerifier,
)


def verifier() -> DemoSignedManifestVerifier:
    file_catalog = DemoEvidenceFileCatalog(settings.demo_evidence_files_path)
    return DemoSignedManifestVerifier(
        DemoEvidenceTrustKeyCatalog(settings.demo_evidence_trust_keys_path),
        file_catalog,
    )


def default_definition() -> DemoEvidenceFileDefinition:
    definition = DemoEvidenceFileCatalog(settings.demo_evidence_files_path).get_for_evidence_type(
        "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY"
    )
    assert definition is not None
    return definition


def test_every_demo_manifest_has_a_valid_public_key_signature() -> None:
    catalog = DemoEvidenceFileCatalog(settings.demo_evidence_files_path)

    results = [
        verifier().verify(item)
        for item in catalog.list_for_evidence_type("CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY")
    ]

    assert len(results) == 4
    assert {item.status for item in results} == {EvidenceTrustStatus.VERIFIED}
    assert {item.rationale_code for item in results} == {"DEMO_SIGNED_MANIFEST_VERIFIED"}
    assert verifier().is_ready() is True


def test_manifest_change_invalidates_the_signature() -> None:
    definition = default_definition()
    changed_manifest = definition.manifest.model_copy(
        update={"business_name": "서명 후 변경된 상호"}
    )
    changed = definition.model_copy(update={"manifest": changed_manifest})

    result = verifier().verify(changed)

    assert result.status == EvidenceTrustStatus.NOT_VERIFIED
    assert result.verified_scopes == []
    assert result.rationale_code == "DEMO_MANIFEST_SIGNATURE_INVALID"


def test_unknown_signing_key_is_not_treated_as_verified() -> None:
    definition = default_definition()
    assert definition.manifest_signature is not None
    changed = definition.model_copy(
        update={
            "manifest_signature": DemoManifestSignature(
                key_id="unknown-demo-key",
                value=definition.manifest_signature.value,
            )
        }
    )

    result = verifier().verify(changed)

    assert result.status == EvidenceTrustStatus.NOT_VERIFIED
    assert result.rationale_code == "DEMO_MANIFEST_SIGNING_KEY_NOT_FOUND"
