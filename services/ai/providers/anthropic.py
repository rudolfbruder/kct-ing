"""Claude, either on Vertex AI or through the Anthropic API (KCT_AI_PROVIDER=anthropic).

KCT_ANTHROPIC_PLATFORM picks the route:
  vertex  Claude on Vertex AI, same Google Cloud project and credentials as Gemini.
  api     Anthropic API, using ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import base64

import anthropic

from services.ai.exceptions import AiConfigurationError, AiProviderError
from services.ai.providers.base import ProviderRequest
from services.ai.responses import ProviderResponse, Usage


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, platform: str, project: str, region: str) -> None:
        if platform == "vertex":
            if not project:
                raise AiConfigurationError("Set KCT_PROJECT_ID to use Claude on Vertex AI.")
            self.client = anthropic.AnthropicVertex(project_id=project, region=region)
        elif platform == "api":
            self.client = anthropic.Anthropic()
        else:
            raise AiConfigurationError(
                f"KCT_ANTHROPIC_PLATFORM must be 'vertex' or 'api', got {platform!r}"
            )

    def prompt(self, request: ProviderRequest) -> ProviderResponse:
        content: list[dict] = [
            {
                "type": "document",
                "title": doc.title,
                "source": {
                    "type": "base64",
                    "media_type": doc.mime_type,
                    "data": base64.standard_b64encode(doc.data).decode("ascii"),
                },
            }
            for doc in request.attachments
        ]
        content.append({"type": "text", "text": request.prompt})

        params: dict = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": request.instructions,
            "messages": [{"role": "user", "content": content}],
        }
        if request.output_schema is not None:
            params["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": anthropic.transform_schema(request.output_schema),
                }
            }

        try:
            # Streaming, because large max_tokens values time out as a single request.
            with self.client.messages.stream(**params) as stream:
                message = stream.get_final_message()
        except anthropic.APIError as exc:
            raise AiProviderError(f"Claude call failed: {exc}") from exc

        if message.stop_reason == "refusal":
            raise AiProviderError(f"Claude declined the request: {message.stop_details}")

        return ProviderResponse(
            text="".join(block.text for block in message.content if block.type == "text"),
            model=message.model,
            usage=Usage(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            ),
            truncated=message.stop_reason == "max_tokens",
        )
