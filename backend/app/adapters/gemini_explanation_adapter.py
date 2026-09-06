import json
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.request import Request, urlopen

from pydantic import SecretStr

from app.adapters.explanation_adapter import ExplanationProvider
from app.schemas.explanation import (
    AssessmentExplanationInputSnapshot,
    ExplanationPlan,
    ExplanationRenderingMode,
)


class GeminiInteractionTransport(Protocol):
    def create(
        self,
        *,
        api_key: SecretStr,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]: ...


class UrlLibGeminiInteractionTransport:
    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
    MAX_RESPONSE_BYTES = 64 * 1024

    def create(
        self,
        *,
        api_key: SecretStr,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        request = Request(
            self.ENDPOINT,
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
    provider_version = "gemini-interactions-explanation-provider-v1"
    rendering_mode = ExplanationRenderingMode.GENERATIVE_AI
    prompt_version = "explanation-message-plan-v2"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        transport: GeminiInteractionTransport | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise ValueError("Gemini API key is required")
        if not model.strip():
            raise ValueError("Gemini model is required")
        self.api_key = api_key
        self.model_version = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport or UrlLibGeminiInteractionTransport()

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
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        output_text = self._extract_output_text(response)
        return ExplanationPlan.model_validate_json(output_text)

    def _build_payload(
        self,
        snapshot: AssessmentExplanationInputSnapshot,
        allowed_message_codes: tuple[str, ...],
    ) -> dict[str, Any]:
        current_state_code = allowed_message_codes[-1]
        return {
            "model": self.model_version,
            "input": (
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
            ),
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": {
                    "type": "object",
                    "properties": {
                        "headlineCode": {
                            "type": "string",
                            "enum": list(allowed_message_codes),
                        },
                        "sectionCodes": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": list(allowed_message_codes),
                            },
                            "minItems": 1,
                            "maxItems": min(8, len(allowed_message_codes)),
                        },
                    },
                    "required": ["headlineCode", "sectionCodes"],
                },
            },
        }

    @staticmethod
    def _extract_output_text(response: Mapping[str, Any]) -> str:
        if response.get("status") != "completed":
            raise ValueError("Gemini interaction did not complete")
        text_blocks: list[str] = []
        steps = response.get("steps")
        if not isinstance(steps, list):
            raise ValueError("Gemini interaction steps are missing")
        for step in steps:
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            content = step.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        text_blocks.append(text)
        if len(text_blocks) != 1:
            raise ValueError("Gemini interaction must return exactly one text output")
        return text_blocks[0]
