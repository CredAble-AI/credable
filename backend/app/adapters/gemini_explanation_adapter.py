import json
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import SecretStr

from app.adapters.explanation_adapter import ExplanationProvider
from app.schemas.explanation import (
    AssessmentExplanationInputSnapshot,
    ExplanationPlan,
    ExplanationRenderingMode,
)


class GeminiGenerateContentTransport(Protocol):
    def create(
        self,
        *,
        api_key: SecretStr,
        model: str,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]: ...


class UrlLibGeminiGenerateContentTransport:
    """Calls the Generative Language API's generateContent endpoint."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    MAX_RESPONSE_BYTES = 64 * 1024

    @classmethod
    def endpoint(cls, model: str) -> str:
        return f"{cls.BASE_URL}/models/{quote(model, safe='')}:generateContent"

    def create(
        self,
        *,
        api_key: SecretStr,
        model: str,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        request = Request(
            self.endpoint(model),
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key.get_secret_value(),
            },
            method="POST",
        )
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            raw = response.read(self.MAX_RESPONSE_BYTES + 1)
        if len(raw) > self.MAX_RESPONSE_BYTES:
            raise ValueError("Gemini response exceeded the configured size limit")
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("Gemini response must be a JSON object")
        return decoded


class GeminiExplanationProvider(ExplanationProvider):
    provider_version = "gemini-generate-content-explanation-provider-v1"
    rendering_mode = ExplanationRenderingMode.GENERATIVE_AI
    prompt_version = "explanation-message-plan-v3"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        transport: GeminiGenerateContentTransport | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise ValueError("Gemini API key is required")
        if not model.strip():
            raise ValueError("Gemini model is required")
        self.api_key = api_key
        self.model_version = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport or UrlLibGeminiGenerateContentTransport()

    def plan(
        self,
        snapshot: AssessmentExplanationInputSnapshot,
        allowed_message_codes: tuple[str, ...],
    ) -> ExplanationPlan:
        if not allowed_message_codes:
            raise ValueError("at least one allowed explanation message code is required")
        payload = self._build_payload(snapshot, allowed_message_codes)
        response = self.transport.create(
            api_key=self.api_key,
            model=self.model_version,
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        return ExplanationPlan.model_validate_json(self._extract_output_text(response))

    def _build_payload(
        self,
        snapshot: AssessmentExplanationInputSnapshot,
        allowed_message_codes: tuple[str, ...],
    ) -> dict[str, Any]:
        current_state_code = allowed_message_codes[-1]
        instruction = (
            "You are a constrained presentation planner for a lending assessment explanation. "
            "Select only from the allowed machine-readable message codes. Never create or infer "
            "credit scores, grades, eligibility, evidence requests, risk, policy routes, approval "
            "or rejection, interest rates, or loan amounts. The required current-state code must "
            "be the headline and must be included in sectionCodes. Keep sectionCodes in the same "
            "relative order as allowedMessageCodes and return no more than eight codes.\n"
            + json.dumps(
                {
                    "targetType": snapshot.target_type.value,
                    "allowedMessageCodes": list(allowed_message_codes),
                    "requiredCurrentStateCode": current_state_code,
                },
                separators=(",", ":"),
            )
        )
        return {
            "contents": [{"role": "user", "parts": [{"text": instruction}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "headlineCode": {
                            "type": "STRING",
                            "enum": list(allowed_message_codes),
                        },
                        "sectionCodes": {
                            "type": "ARRAY",
                            "items": {
                                "type": "STRING",
                                "enum": list(allowed_message_codes),
                            },
                            "minItems": 1,
                            "maxItems": min(8, len(allowed_message_codes)),
                        },
                    },
                    "required": ["headlineCode", "sectionCodes"],
                    "propertyOrdering": ["headlineCode", "sectionCodes"],
                },
            },
        }

    @staticmethod
    def _extract_output_text(response: Mapping[str, Any]) -> str:
        candidates = response.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise ValueError("Gemini response must return exactly one candidate")
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise ValueError("Gemini candidate must be an object")
        finish_reason = candidate.get("finishReason")
        if finish_reason not in (None, "STOP"):
            raise ValueError(f"Gemini generation did not complete: {finish_reason}")
        content = candidate.get("content")
        if not isinstance(content, dict):
            raise ValueError("Gemini candidate content is missing")
        parts = content.get("parts")
        if not isinstance(parts, list):
            raise ValueError("Gemini candidate parts are missing")
        text_parts = [
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip()
        ]
        if len(text_parts) != 1:
            raise ValueError("Gemini response must return exactly one text part")
        return text_parts[0]
