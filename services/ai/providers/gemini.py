"""Gemini on Vertex AI (KCT_AI_PROVIDER=gemini)."""
from __future__ import annotations

from google import genai
from google.genai import types

from services.ai.exceptions import AiConfigurationError, AiProviderError
from services.ai.providers.base import ProviderRequest
from services.ai.responses import ProviderResponse, Usage


class GeminiProvider:
    name = "gemini"

    def __init__(self, project: str, location: str) -> None:
        if not project:
            raise AiConfigurationError("Set KCT_PROJECT_ID to use Gemini.")
        self.client = genai.Client(vertexai=True, project=project, location=location)

    def prompt(self, request: ProviderRequest) -> ProviderResponse:
        parts: list[types.Part] = []
        for doc in request.attachments:
            # Gemini has no document titles, so name each document in a text part before it.
            parts.append(types.Part.from_text(text=f"Document: {doc.title}"))
            parts.append(types.Part.from_bytes(data=doc.data, mime_type=doc.mime_type))
        parts.append(types.Part.from_text(text=request.prompt))

        config = types.GenerateContentConfig(
            system_instruction=request.instructions,
            temperature=request.temperature,
            # On gemini-2.5-pro, thinking tokens count against this limit.
            max_output_tokens=request.max_tokens,
        )
        if request.output_schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = request.output_schema

        try:
            response = self.client.models.generate_content(
                model=request.model,
                contents=[types.Content(role="user", parts=parts)],
                config=config,
            )
        except Exception as exc:
            raise AiProviderError(f"Gemini call failed: {exc}") from exc

        candidate = response.candidates[0] if response.candidates else None
        if candidate is None:
            raise AiProviderError(f"Gemini returned no answer: {response.prompt_feedback}")

        usage = response.usage_metadata
        return ProviderResponse(
            text=response.text or "",
            model=response.model_version or request.model,
            usage=Usage(
                input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            ),
            truncated=candidate.finish_reason == types.FinishReason.MAX_TOKENS,
        )
