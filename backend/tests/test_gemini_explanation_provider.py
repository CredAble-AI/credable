import json
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import SecretStr

import app.adapters.gemini_explanation_adapter as gemini_adapter_module
from app.adapters.explanation_adapter import DemoExplanationProvider
from app.adapters.gemini_explanation_adapter import (
    GeminiExplanationProvider,
    UrlLibGeminiGenerateContentTransport,
)
from app.core.config import ExplanationProviderMode, Settings
from app.main import build_explanation_provider
from app.schemas.explanation import (
    AssessmentExplanationInputSnapshot,
    ExplanationFact,
    ExplanationRenderingMode,
    ExplanationSourceReference,
    ExplanationSourceType,
    ExplanationTargetType,
)


class FakeGeminiTransport:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.api_key: SecretStr | None = None
        self.model: str | None = None
        self.payload: Mapping[str, Any] | None = None
        self.timeout_seconds: float | None = None

    def create(
        self,
        *,
        api_key: SecretStr,
        model: str,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.api_key = api_key
        self.model = model
        self.payload = payload
        self.timeout_seconds = timeout_seconds
        return self.response


class FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _: int) -> bytes:
        return self.body


def make_snapshot() -> AssessmentExplanationInputSnapshot:
    return AssessmentExplanationInputSnapshot(
        session_id="ses_private_identifier",
        target_type=ExplanationTargetType.BASELINE_ASSESSMENT,
        target_assessment_id="asm_private_identifier",
        facts=[
            ExplanationFact(
                fact_code="BASELINE_GRADE_SET",
                source_reference_id="asm_private_identifier",
                values=["private-financial-value"],
            )
        ],
        source_references=[
            ExplanationSourceReference(
                source_type=ExplanationSourceType.BASELINE_ASSESSMENT,
                source_id="asm_private_identifier",
                data_version="private-data-version",
            )
        ],
    )


def completed_response(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"role": "model", "parts": [{"text": json.dumps(plan)}]},
            }
        ]
    }


def test_http_transport_targets_generate_content_without_exposing_the_key(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout: float):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeHttpResponse(b'{"candidates":[]}')

    monkeypatch.setattr(gemini_adapter_module, "urlopen", fake_urlopen)
    transport = UrlLibGeminiGenerateContentTransport()

    response = transport.create(
        api_key=SecretStr("synthetic-test-key"),
        model="gemini-2.5-flash-lite",
        payload={"contents": [{"role": "user", "parts": [{"text": "safe-codes-only"}]}]},
        timeout_seconds=5,
    )

    request = captured["request"]
    assert response == {"candidates": []}
    assert captured["timeout"] == 5
    # The model belongs in the path of the documented generateContent endpoint.
    assert request.full_url == (
        "https://generativelanguage.googleapis.com/v1beta"
        "/models/gemini-2.5-flash-lite:generateContent"
    )
    assert "synthetic-test-key" not in request.full_url
    assert b"synthetic-test-key" not in request.data
    assert request.get_header("X-goog-api-key") == "synthetic-test-key"


def test_gemini_provider_sends_only_allowed_codes_and_parses_structured_plan() -> None:
    allowed_codes = (
        "BASELINE_RESULT_AVAILABLE",
        "BASELINE_UNCERTAINTY_PRESENT",
        "POLICY_PATH_AMBIGUOUS",
    )
    transport = FakeGeminiTransport(
        completed_response(
            {
                "headlineCode": "POLICY_PATH_AMBIGUOUS",
                "sectionCodes": list(allowed_codes),
            }
        )
    )
    provider = GeminiExplanationProvider(
        api_key=SecretStr("synthetic-test-key"),
        model="gemini-2.5-flash-lite",
        timeout_seconds=7,
        transport=transport,
    )

    plan = provider.plan(make_snapshot(), allowed_codes)

    assert plan.headline_code == "POLICY_PATH_AMBIGUOUS"
    assert plan.section_codes == list(allowed_codes)
    assert transport.timeout_seconds == 7
    assert isinstance(transport.api_key, SecretStr)
    assert transport.model == "gemini-2.5-flash-lite"
    assert transport.payload is not None
    prompt = transport.payload["contents"][0]["parts"][0]["text"]
    assert isinstance(prompt, str)
    assert all(code in prompt for code in allowed_codes)
    assert "ses_private_identifier" not in prompt
    assert "asm_private_identifier" not in prompt
    assert "private-financial-value" not in prompt
    assert "private-data-version" not in prompt
    generation_config = transport.payload["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    schema = generation_config["responseSchema"]
    assert schema["properties"]["headlineCode"]["enum"] == list(allowed_codes)
    assert schema["properties"]["sectionCodes"]["items"]["enum"] == list(allowed_codes)


@pytest.mark.parametrize(
    "response",
    [
        {"candidates": []},
        {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}}]},
        {"candidates": [{"finishReason": "STOP"}]},
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": "{}"}, {"text": "{}"}]},
                }
            ]
        },
    ],
)
def test_gemini_provider_rejects_incomplete_or_ambiguous_output(
    response: Mapping[str, Any],
) -> None:
    provider = GeminiExplanationProvider(
        api_key=SecretStr("synthetic-test-key"),
        model="gemini-2.5-flash-lite",
        timeout_seconds=7,
        transport=FakeGeminiTransport(response),
    )

    with pytest.raises(ValueError):
        provider.plan(make_snapshot(), ("BASELINE_RESULT_AVAILABLE",))


def test_provider_factory_defaults_to_demo() -> None:
    provider = build_explanation_provider(
        Settings(explanation_provider=ExplanationProviderMode.DEMO)
    )

    assert isinstance(provider, DemoExplanationProvider)


def test_provider_factory_requires_key_for_gemini() -> None:
    with pytest.raises(ValueError, match="GEMINI_API_KEY is required"):
        build_explanation_provider(
            Settings(
                explanation_provider=ExplanationProviderMode.GEMINI,
                gemini_api_key=None,
            )
        )


def test_provider_factory_builds_generative_gemini_provider() -> None:
    provider = build_explanation_provider(
        Settings(
            explanation_provider=ExplanationProviderMode.GEMINI,
            gemini_api_key=SecretStr("synthetic-test-key"),
            gemini_model="gemini-2.5-flash-lite",
            gemini_timeout_seconds=9,
        )
    )

    assert isinstance(provider, GeminiExplanationProvider)
    assert provider.rendering_mode == ExplanationRenderingMode.GENERATIVE_AI
    assert provider.model_version == "gemini-2.5-flash-lite"
    assert provider.timeout_seconds == 9
    assert "synthetic-test-key" not in repr(provider.api_key)
