"""Answers from fixture files instead of a model (KCT_AI_PROVIDER=fake).

Each agent gets the file named after it in the fixtures folder, for example
tests/fixtures/fake_ai/test_steps.json for the "test_steps" agent. The answer
is the same whatever documents are attached, but everything around it behaves
as with a real provider: token usage is reported, and an answer longer than
max_tokens comes back truncated, so a too-low limit fails the same way.
"""
from __future__ import annotations

from pathlib import Path

from services.ai.exceptions import AiConfigurationError
from services.ai.providers.base import ProviderRequest
from services.ai.responses import ProviderResponse, Usage


def estimate_tokens(text: str) -> int:
    # Roughly four characters per token, close enough for English.
    return max(1, len(text) // 4)


class FakeProvider:
    name = "fake"

    def __init__(self, fixtures: Path) -> None:
        self.fixtures = fixtures

    def prompt(self, request: ProviderRequest) -> ProviderResponse:
        text = self._fixture(request.agent).read_text(encoding="utf-8")

        # Vertex bills a PDF at about 258 tokens per page; assume ~50 KB a page.
        input_tokens = estimate_tokens(request.instructions + request.prompt) + sum(
            258 * max(1, len(doc.data) // 50_000) for doc in request.attachments
        )
        output_tokens = estimate_tokens(text)

        truncated = output_tokens > request.max_tokens
        if truncated:
            text = text[: request.max_tokens * 4]
            output_tokens = request.max_tokens

        return ProviderResponse(
            text=text,
            model=request.model,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            truncated=truncated,
        )

    def _fixture(self, agent: str) -> Path:
        for suffix in (".json", ".md", ".txt"):
            path = self.fixtures / f"{agent}{suffix}"
            if path.is_file():
                return path
        raise AiConfigurationError(f"No fake answer for agent {agent!r} in {self.fixtures}")
