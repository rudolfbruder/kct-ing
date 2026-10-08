"""Thin wrapper around Gemini on Vertex AI.

The only place in the codebase that talks to the model. Everything else works
with plain strings and file paths, which keeps the services testable without a
network call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types

from .config import settings


@dataclass
class ModelReply:
    text: str
    usage: dict[str, int] = field(default_factory=dict)


_client: genai.Client | None = None


def client() -> genai.Client:
    """Lazily created singleton, so importing the module needs no credentials."""
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=settings.require_project(),
            location=settings.location,
        )
    return _client


def file_part(path: Path, mime_type: str) -> types.Part:
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)


def generate(
    system_instruction: str,
    parts: list[types.Part],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    response_mime_type: str | None = None,
) -> ModelReply:
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=settings.temperature if temperature is None else temperature,
        max_output_tokens=max_output_tokens or settings.max_output_tokens,
        response_mime_type=response_mime_type,
    )
    response = client().models.generate_content(
        model=model or settings.model,
        contents=[types.Content(role="user", parts=parts)],
        config=config,
    )

    usage: dict[str, int] = {}
    meta = getattr(response, "usage_metadata", None)
    if meta is not None:
        usage = {
            "prompt_tokens": getattr(meta, "prompt_token_count", 0) or 0,
            "candidates_tokens": getattr(meta, "candidates_token_count", 0) or 0,
            "total_tokens": getattr(meta, "total_token_count", 0) or 0,
        }

    text = (response.text or "").strip()
    if not text:
        raise RuntimeError(
            "Model returned no text. Check the finish reason and any safety blocks."
        )
    return ModelReply(text=text, usage=usage)
