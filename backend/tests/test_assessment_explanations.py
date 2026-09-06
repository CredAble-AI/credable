from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    DemoAssessmentAdapter,
    DemoSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.adapters.explanation_adapter import ExplanationProvider
from app.core.config import settings
from app.schemas.audit import AuditStage
from app.schemas.explanation import (
    AssessmentExplanationInputSnapshot,
    ExplanationPlan,
    ExplanationRenderingMode,
)
from app.services.assessment_service import AssessmentService, SupplementalAssessmentService
from app.services.data_source_service import DataSourceService


class FailingExplanationProvider(ExplanationProvider):
    provider_version = "failing-provider-v1"
    rendering_mode = ExplanationRenderingMode.GENERATIVE_AI
    model_version = "failing-model-v1"
    prompt_version = "failing-prompt-v1"

    def plan(
        self,
        snapshot: AssessmentExplanationInputSnapshot,
        allowed_message_codes: tuple[str, ...],
    ) -> ExplanationPlan:
        del snapshot, allowed_message_codes
        raise RuntimeError("synthetic provider failure")


class InvalidExplanationProvider(ExplanationProvider):
    provider_version = "invalid-provider-v1"
    rendering_mode = ExplanationRenderingMode.GENERATIVE_AI
    model_version = "invalid-model-v1"
    prompt_version = "invalid-prompt-v1"

    def plan(
        self,
        snapshot: AssessmentExplanationInputSnapshot,
        allowed_message_codes: tuple[str, ...],
    ) -> ExplanationPlan:
        del snapshot, allowed_message_codes
        return ExplanationPlan(
            headline_code="UNSUPPORTED_APPROVAL_CLAIM",
            section_codes=["UNSUPPORTED_APPROVAL_CLAIM"],
        )


class ReorderedExplanationProvider(ExplanationProvider):
    provider_version = "reordered-provider-v1"
    rendering_mode = ExplanationRenderingMode.GENERATIVE_AI
    model_version = "reordered-model-v1"
    prompt_version = "reordered-prompt-v1"

    def plan(
        self,
        snapshot: AssessmentExplanationInputSnapshot,
        allowed_message_codes: tuple[str, ...],
    ) -> ExplanationPlan:
        del snapshot
        return ExplanationPlan(
            headline_code=allowed_message_codes[-1],
            section_codes=list(reversed(allowed_message_codes)),
        )


def create_session(client: TestClient) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"businessBorrowerType": "SOLE_PROPRIETOR"},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def run_baseline(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> tuple[str, dict]:
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    session_id = create_session(client)
    for source_type in ("BANK_INTERNAL", "CREDIT_INFORMATION"):
        assert (
            client.post(f"/v1/sessions/{session_id}/consents/{source_type}/grant").status_code
            == 200
        )
    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200
    response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    assert response.status_code == 200
    return session_id, response.json()["assessment"]


def test_explanation_requires_an_executed_assessment(client: TestClient) -> None:
    session_id = create_session(client)

    empty = client.get(f"/v1/sessions/{session_id}/assessment/explanation")
    response = client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")

    assert empty.status_code == 200
    assert empty.json() == {"sessionId": session_id, "explanation": None}
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSESSMENT_EXPLANATION_TARGET_NOT_READY"


def test_demo_provider_renders_only_server_allowed_baseline_messages(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id, assessment = run_baseline(client, data_source_service, assessment_service)

    first = client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")
    repeated = client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")

    assert first.status_code == 200
    explanation = first.json()["explanation"]
    assert explanation["targetType"] == "BASELINE_ASSESSMENT"
    assert explanation["targetAssessmentId"] == assessment["assessmentId"]
    assert explanation["renderingMode"] == "DEMO_TEMPLATE"
    assert explanation["fallbackApplied"] is False
    assert explanation["fallbackReasonCode"] is None
    assert explanation["modelVersion"] is None
    assert explanation["providerVersion"] == "demo-explanation-provider-v1"
    assert [section["messageCode"] for section in explanation["sections"]] == [
        "BASELINE_RESULT_AVAILABLE",
        "BASELINE_UNCERTAINTY_PRESENT",
    ]
    assert {item["sourceType"] for item in explanation["sourceReferences"]} == {
        "BASELINE_ASSESSMENT"
    }
    assert "pointEstimate" not in first.text
    assert "lowerBound" not in first.text
    assert "upperBound" not in first.text
    assert repeated.json()["explanation"]["explanationId"] == explanation["explanationId"]
    assert client.app.state.assessment_explanation_service.repository.count(session_id) == 1

    events = assessment_service.session_service.repository.list_audit_events(session_id)
    assert events[-1].stage == AuditStage.ASSESSMENT_EXPLANATION_GENERATED
    assert events[-1].input_snapshot_hash == explanation["inputSnapshotHash"]
    assert events[-1].output_summary["fallbackApplied"] is False

    assert client.post(f"/v1/sessions/{session_id}/assessment/boundary-check").status_code == 200
    stale = client.get(f"/v1/sessions/{session_id}/assessment/explanation")
    refreshed = client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")
    assert stale.json()["explanation"] is None
    assert refreshed.json()["explanation"]["explanationId"] != explanation["explanationId"]
    assert refreshed.json()["explanation"]["sections"][-1]["messageCode"] == (
        "POLICY_PATH_AMBIGUOUS"
    )
    assert client.app.state.assessment_explanation_service.repository.count(session_id) == 2


def test_explanation_tracks_supplemental_comparison_and_resolution_lineage(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
) -> None:
    session_id, _ = run_baseline(client, data_source_service, assessment_service)
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        settings.demo_supplemental_assessments_path
    )
    assert client.post(f"/v1/sessions/{session_id}/assessment/boundary-check").status_code == 200
    selection_response = client.post(f"/v1/sessions/{session_id}/evidence/next")
    selection_id = selection_response.json()["selection"]["selectionId"]
    submission_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": selection_id,
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    )
    submission_id = submission_response.json()["submission"]["submissionId"]
    assert (
        client.post(
            f"/v1/sessions/{session_id}/evidence/submissions/{submission_id}/quality"
        ).status_code
        == 200
    )
    supplemental_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json={"submissionId": submission_id},
    )
    assert supplemental_response.status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/comparison").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/resolution").status_code == 200

    response = client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")

    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert explanation["targetType"] == "SUPPLEMENTAL_ASSESSMENT"
    assert (
        explanation["targetAssessmentId"]
        == (supplemental_response.json()["supplementalAssessment"]["supplementalAssessmentId"])
    )
    assert [section["messageCode"] for section in explanation["sections"]][-3:] == [
        "SUPPLEMENTAL_RESULT_AVAILABLE",
        "UNCERTAINTY_NARROWED",
        "COLLECTION_RESOLVED",
    ]
    assert {item["sourceType"] for item in explanation["sourceReferences"]} == {
        "BASELINE_ASSESSMENT",
        "POLICY_BOUNDARY",
        "SUPPLEMENTAL_ASSESSMENT",
        "ASSESSMENT_COMPARISON",
        "EVIDENCE_RESOLUTION",
    }
    assert all(
        set(section["sourceReferenceIds"]).issubset(
            {item["sourceId"] for item in explanation["sourceReferences"]}
        )
        for section in explanation["sections"]
    )


def test_provider_failure_uses_traceable_rule_fallback(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id, _ = run_baseline(client, data_source_service, assessment_service)
    client.app.state.assessment_explanation_service.provider = FailingExplanationProvider()

    response = client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")

    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert explanation["renderingMode"] == "RULE_FALLBACK"
    assert explanation["fallbackApplied"] is True
    assert explanation["fallbackReasonCode"] == "EXPLANATION_PROVIDER_ERROR"
    assert explanation["providerVersion"] == "rule-explanation-fallback-v1"
    assert explanation["modelVersion"] is None
    assert "synthetic provider failure" not in response.text
    events = assessment_service.session_service.repository.list_audit_events(session_id)
    assert events[-1].output_summary["fallbackReasonCode"] == "EXPLANATION_PROVIDER_ERROR"


def test_unapproved_provider_message_code_is_replaced_by_rule_fallback(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id, _ = run_baseline(client, data_source_service, assessment_service)
    client.app.state.assessment_explanation_service.provider = InvalidExplanationProvider()

    response = client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")

    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert explanation["renderingMode"] == "RULE_FALLBACK"
    assert explanation["fallbackReasonCode"] == "EXPLANATION_PROVIDER_OUTPUT_INVALID"
    assert "UNSUPPORTED_APPROVAL_CLAIM" not in response.text


def test_provider_cannot_reorder_server_owned_messages(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
) -> None:
    session_id, _ = run_baseline(client, data_source_service, assessment_service)
    client.app.state.assessment_explanation_service.provider = ReorderedExplanationProvider()

    response = client.post(f"/v1/sessions/{session_id}/assessment/explanation/generate")

    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert explanation["renderingMode"] == "RULE_FALLBACK"
    assert explanation["fallbackReasonCode"] == "EXPLANATION_PROVIDER_OUTPUT_INVALID"
    assert [section["messageCode"] for section in explanation["sections"]] == [
        "BASELINE_RESULT_AVAILABLE",
        "BASELINE_UNCERTAINTY_PRESENT",
    ]
