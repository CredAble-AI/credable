"""Sign Demo Evidence manifests with an external RSA private key.

The private key is read from the provided path and is never copied into the repository.
"""

import argparse
import base64
import json
import subprocess
import tempfile
from pathlib import Path

from app.schemas.evidence_file import DemoEvidenceFileCatalogData
from app.services.evidence_trust_service import canonical_manifest_payload

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_CATALOG = BACKEND_ROOT / "app/data/demo_evidence_files.json"
DEFAULT_KEY_CATALOG = BACKEND_ROOT / "app/data/demo_evidence_trust_keys.json"


def _run(*command: str) -> bytes:
    return subprocess.run(command, check=True, capture_output=True).stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--key-id", default="credable-demo-manifest-rs256-v1")
    parser.add_argument("--evidence-catalog", type=Path, default=DEFAULT_EVIDENCE_CATALOG)
    parser.add_argument("--key-catalog", type=Path, default=DEFAULT_KEY_CATALOG)
    args = parser.parse_args()

    raw_catalog = json.loads(args.evidence_catalog.read_text(encoding="utf-8"))
    catalog = DemoEvidenceFileCatalogData.model_validate(raw_catalog)
    definitions = {item.demo_file_id: item for item in catalog.files}

    for raw_definition in raw_catalog["files"]:
        definition = definitions[raw_definition["demoFileId"]]
        with tempfile.NamedTemporaryFile() as payload_file:
            payload_file.write(canonical_manifest_payload(definition))
            payload_file.flush()
            signature = _run(
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(args.private_key),
                payload_file.name,
            )
        raw_definition["manifestSignature"] = {
            "algorithm": "RS256",
            "keyId": args.key_id,
            "value": base64.b64encode(signature).decode(),
        }

    modulus_output = (
        _run(
            "openssl",
            "rsa",
            "-in",
            str(args.private_key),
            "-noout",
            "-modulus",
        )
        .decode()
        .strip()
    )
    modulus_hex = modulus_output.removeprefix("Modulus=").lower()
    key_catalog = {
        "dataVersion": "demo-evidence-trust-keys-v1",
        "keys": [
            {
                "keyId": args.key_id,
                "algorithm": "RS256",
                "modulusHex": modulus_hex,
                "publicExponent": 65537,
            }
        ],
        "demoOnly": True,
    }
    args.evidence_catalog.write_text(
        json.dumps(raw_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.key_catalog.write_text(
        json.dumps(key_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
