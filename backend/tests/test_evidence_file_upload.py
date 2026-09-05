import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import DemoAssessmentAdapter, DemoSupplementalAssessmentAdapter
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.core.config import settings
from app.repositories.evidence_submission_repository import SqliteEvidenceSubmissionRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService, SupplementalAssessmentService
from app.services.data_source_service import DataSourceService
from app.services.evidence_quality_service import EvidenceQualityService
from app.services.evidence_submission_service import DemoEvidenceFileCatalog


def create_session(client: TestClient) -> str:
    response = client.post("/v1/sessions/demo", json={"businessBorrowerType": "SOLE_PROPRIETOR"})
    assert response.status_code == 201
    return response.json()["sessionId"]


def prepare_selection(
    client: TestClient,
    session_id: str,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> dict:
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    for source_type in (
        ConsentSourceType.BANK_INTERNAL,
        ConsentSourceType.CREDIT_INFORMATION,
    ):
        response = client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant")
        assert response.status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/run").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/boundary-check").status_code == 200
    response = client.post(f"/v1/sessions/{session_id}/evidence/next")
    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["status"] == "SELECTED"
    assert selection["selectedEvidence"]["collectionMode"] == "DEMO_FILE_UPLOAD"
    return selection


def grant_evidence_consent(
    client: TestClient,
    session_id: str,
    selection_id: str,
) -> None:
    response = client.post(
        f"/v1/sessions/{session_id}/evidence/selections/{selection_id}/consent/grant"
    )
    assert response.status_code == 200


def demo_pdf_path() -> Path:
    return settings.demo_evidence_files_path.parent / "demo_files/recent_revenue_summary_v1.pdf"


def upload(
    client: TestClient,
    session_id: str,
    selection_id: str,
    content: bytes,
    *,
    file_name: str = "최근_매출_입금_요약서_DEMO.pdf",
    content_type: str = "application/pdf",
):
    return client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/upload",
        data={"selectionId": selection_id},
        files={"file": (file_name, content, content_type)},
    )


def test_submission_option_reflects_current_consent_and_server_file(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    endpoint = (
        f"/v1/sessions/{session_id}/evidence/selections/"
        f"{selection['selectionId']}/submission-option"
    )

    before = client.get(endpoint)
    client.post(
        f"/v1/sessions/{session_id}/consents/{ConsentSourceType.CUSTOMER_SUBMITTED.value}/grant"
    )
    after = client.get(endpoint)

    assert before.status_code == 200
    option = before.json()
    assert option["collectionMode"] == "DEMO_FILE_UPLOAD"
    assert option["submissionRequirement"] == {
        "status": "CONSENT_REQUIRED",
        "reasonCode": "EVIDENCE_SELECTION_CONSENT_REQUIRED",
        "consentSourceType": "CUSTOMER_SUBMITTED",
    }
    assert option["demoFile"]["demoFileId"] == "demo_recent_revenue_summary_v1"
    assert option["demoFile"]["contentType"] == "application/pdf"
    assert option["demoFile"]["sizeBytes"] == demo_pdf_path().stat().st_size
    assert option["demoFile"]["downloadUrl"].endswith("/demo-file/download")
    assert option["uploadPolicy"] == {
        "allowedContentTypes": ["application/pdf"],
        "allowedExtensions": [".pdf"],
        "maxSizeBytes": 5 * 1024 * 1024,
    }
    assert after.json()["submissionRequirement"]["status"] == "CONSENT_REQUIRED"
    grant_evidence_consent(client, session_id, selection["selectionId"])
    ready = client.get(endpoint).json()["submissionRequirement"]
    assert ready["status"] == "READY"
    assert ready["reasonCode"] is None


def test_other_session_cannot_access_selection_file_contract(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    owner_session_id = create_session(client)
    selection = prepare_selection(
        client,
        owner_session_id,
        data_source_service,
        assessment_service,
    )
    other_session_id = create_session(client)

    response = client.get(
        f"/v1/sessions/{other_session_id}/evidence/selections/"
        f"{selection['selectionId']}/submission-option"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVIDENCE_SELECTION_NOT_FOUND"


def test_demo_pdf_download_uses_safe_attachment_headers(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    grant_evidence_consent(client, session_id, selection["selectionId"])

    response = client.get(
        f"/v1/sessions/{session_id}/evidence/selections/"
        f"{selection['selectionId']}/demo-file/download"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.content == demo_pdf_path().read_bytes()
    assert response.content.startswith(b"%PDF-")


def test_demo_pdf_download_requires_selection_scoped_consent(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)

    response = client.get(
        f"/v1/sessions/{session_id}/evidence/selections/"
        f"{selection['selectionId']}/demo-file/download"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_CONSENT_REQUIRED"


def test_upload_requires_current_customer_submitted_consent(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)

    response = upload(
        client,
        session_id,
        selection["selectionId"],
        demo_pdf_path().read_bytes(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_CONSENT_REQUIRED"


def test_valid_demo_pdf_upload_preserves_only_verified_metadata(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    grant_evidence_consent(client, session_id, selection["selectionId"])
    pdf_content = demo_pdf_path().read_bytes()

    response = upload(client, session_id, selection["selectionId"], pdf_content)

    assert response.status_code == 200
    submission = response.json()["submission"]
    assert submission["submissionMode"] == "DEMO_FILE_UPLOAD"
    assert submission["evidenceConsentId"].startswith("evc_")
    assert submission["consentScopeVersion"] == "demo-recent-revenue-consent-v1"
    assert submission["uploadedFile"] == {
        "demoFileId": "demo_recent_revenue_summary_v1",
        "fileName": "최근_매출_입금_요약서_DEMO.pdf",
        "contentType": "application/pdf",
        "sizeBytes": len(pdf_content),
        "sha256": "dcb17cca7569a46073f3b23e1e5eb0a0fbc0e7707995be056b557cb81bf6128d",
    }
    stored = evidence_submission_repository.get_by_submission_id(submission["submissionId"])
    assert stored is not None
    assert stored.uploaded_file is not None
    database_content = evidence_submission_repository.database_path.read_bytes()
    assert pdf_content not in database_content
    assert b"%PDF-" not in database_content
    event = session_repository.list_audit_events(session_id)[-1]
    assert event.output_summary["demoFileId"] == "demo_recent_revenue_summary_v1"
    assert "uploadedFileSha256" in event.output_summary
    assert "%PDF-" not in event.model_dump_json()


@pytest.mark.parametrize(
    ("file_name", "content_type", "content_kind", "status_code", "error_code"),
    [
        ("evidence.pdf", "text/plain", "official", 415, "EVIDENCE_FILE_TYPE_UNSUPPORTED"),
        ("evidence.txt", "application/pdf", "official", 415, "EVIDENCE_FILE_TYPE_UNSUPPORTED"),
        ("evidence.pdf", "application/pdf", "invalid_magic", 422, "EVIDENCE_FILE_CONTENT_INVALID"),
        ("evidence.pdf", "application/pdf", "too_large", 413, "EVIDENCE_FILE_TOO_LARGE"),
        ("evidence.pdf", "application/pdf", "different_pdf", 409, "DEMO_EVIDENCE_FILE_MISMATCH"),
    ],
)
def test_upload_rejects_invalid_file_or_unissued_pdf(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    file_name: str,
    content_type: str,
    content_kind: str,
    status_code: int,
    error_code: str,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    grant_evidence_consent(client, session_id, selection["selectionId"])
    content = {
        "official": demo_pdf_path().read_bytes(),
        "invalid_magic": b"not a pdf",
        "too_large": b"%PDF-" + b"x" * (5 * 1024 * 1024),
        "different_pdf": b"%PDF-1.4\n%%EOF",
    }[content_kind]

    response = upload(
        client,
        session_id,
        selection["selectionId"],
        content,
        file_name=file_name,
        content_type=content_type,
    )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == error_code


def test_upload_is_idempotent_for_same_hash_and_conflicts_for_changed_file(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    grant_evidence_consent(client, session_id, selection["selectionId"])
    content = demo_pdf_path().read_bytes()

    first = upload(client, session_id, selection["selectionId"], content)
    second = upload(client, session_id, selection["selectionId"], content)
    changed = upload(
        client,
        session_id,
        selection["selectionId"],
        b"%PDF-1.4\nchanged\n%%EOF",
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "EVIDENCE_ALREADY_SUBMITTED"
    assert evidence_submission_repository.count_submissions(session_id) == 1


def test_uploaded_binary_quality_comes_from_hash_and_manifest_validation(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    grant_evidence_consent(client, session_id, selection["selectionId"])
    submission = upload(
        client,
        session_id,
        selection["selectionId"],
        demo_pdf_path().read_bytes(),
    ).json()["submission"]

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["status"] == "ACCEPTED"
    assert quality["qualityPolicyVersion"] == "demo-binary-evidence-quality-policy-v1"
    assert {item["dimension"] for item in quality["checks"]} == {
        "PROVENANCE",
        "FRESHNESS",
        "AUTHENTICITY",
        "COMPLETENESS",
        "CONSISTENCY",
        "MANIPULATION_RISK",
    }
    assert {item["status"] for item in quality["checks"]} == {"PASSED"}
    assert quality["eligibleForReassessment"] is True


def test_withdrawn_evidence_consent_blocks_new_quality_check(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    selection_id = selection["selectionId"]
    grant_evidence_consent(client, session_id, selection_id)
    submission = upload(
        client,
        session_id,
        selection_id,
        demo_pdf_path().read_bytes(),
    ).json()["submission"]
    client.post(f"/v1/sessions/{session_id}/evidence/selections/{selection_id}/consent/withdraw")

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_CONSENT_NOT_ACTIVE"


def test_withdrawn_evidence_consent_blocks_new_supplemental_assessment(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    selection_id = selection["selectionId"]
    grant_evidence_consent(client, session_id, selection_id)
    submission = upload(
        client,
        session_id,
        selection_id,
        demo_pdf_path().read_bytes(),
    ).json()["submission"]
    quality = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )
    assert quality.status_code == 200
    assert quality.json()["quality"]["status"] == "ACCEPTED"
    withdrawn = client.post(
        f"/v1/sessions/{session_id}/evidence/selections/{selection_id}/consent/withdraw"
    )
    assert withdrawn.status_code == 200

    response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json={"submissionId": submission["submissionId"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_CONSENT_NOT_ACTIVE"


def test_withdrawal_preserves_already_created_supplemental_snapshot(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    selection_id = selection["selectionId"]
    grant_evidence_consent(client, session_id, selection_id)
    submission = upload(
        client,
        session_id,
        selection_id,
        demo_pdf_path().read_bytes(),
    ).json()["submission"]
    quality = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )
    assert quality.status_code == 200
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        settings.demo_supplemental_assessments_path
    )
    endpoint = f"/v1/sessions/{session_id}/assessment/supplemental/run"
    first = client.post(endpoint, json={"submissionId": submission["submissionId"]})
    assert first.status_code == 200

    client.post(f"/v1/sessions/{session_id}/evidence/selections/{selection_id}/consent/withdraw")
    repeated = client.post(endpoint, json={"submissionId": submission["submissionId"]})
    latest = client.get(f"/v1/sessions/{session_id}/assessment/supplemental")

    assert repeated.status_code == 200
    assert repeated.json() == first.json()
    assert latest.json() == first.json()


def test_inconsistent_server_manifest_rejects_uploaded_binary_quality(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_quality_service: EvidenceQualityService,
    tmp_path: Path,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    grant_evidence_consent(client, session_id, selection["selectionId"])
    submission = upload(
        client,
        session_id,
        selection["selectionId"],
        demo_pdf_path().read_bytes(),
    ).json()["submission"]
    catalog_data = json.loads(settings.demo_evidence_files_path.read_text(encoding="utf-8"))
    catalog_data["files"][0]["manifest"]["totals"]["salesAmount"] += 1
    fixture_root = tmp_path / "file-catalog"
    fixture_file_dir = fixture_root / "demo_files"
    fixture_file_dir.mkdir(parents=True)
    shutil.copyfile(demo_pdf_path(), fixture_file_dir / "recent_revenue_summary_v1.pdf")
    fixture_path = fixture_root / "demo_evidence_files.json"
    fixture_path.write_text(json.dumps(catalog_data, ensure_ascii=False), encoding="utf-8")
    evidence_quality_service.file_catalog = DemoEvidenceFileCatalog(fixture_path)

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["status"] == "REJECTED"
    assert quality["eligibleForReassessment"] is False
    consistency = next(item for item in quality["checks"] if item["dimension"] == "CONSISTENCY")
    assert consistency == {
        "dimension": "CONSISTENCY",
        "status": "FAILED",
        "rationaleCode": "DEMO_MANIFEST_TOTALS_INCONSISTENT",
    }


def test_changed_submission_snapshot_is_not_eligible_for_reassessment(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
) -> None:
    session_id = create_session(client)
    selection = prepare_selection(client, session_id, data_source_service, assessment_service)
    grant_evidence_consent(client, session_id, selection["selectionId"])
    submission = upload(
        client,
        session_id,
        selection["selectionId"],
        demo_pdf_path().read_bytes(),
    ).json()["submission"]
    with sqlite3.connect(evidence_submission_repository.database_path) as connection:
        row = connection.execute(
            "SELECT state_json FROM evidence_submissions WHERE submission_id = ?",
            (submission["submissionId"],),
        ).fetchone()
        state = json.loads(row[0])
        state["dataVersion"] = "tampered-data-version"
        connection.execute(
            "UPDATE evidence_submissions SET state_json = ? WHERE submission_id = ?",
            (json.dumps(state, ensure_ascii=False), submission["submissionId"]),
        )

    response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["status"] == "REJECTED"
    assert quality["eligibleForReassessment"] is False
    assert "DEMO_SERVER_DOCUMENT_PROVENANCE_INVALID" in quality["rejectionCodes"]
