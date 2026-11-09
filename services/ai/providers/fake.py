"""Answers from fixture files instead of a model (KCT_AI_PROVIDER=fake).

Each agent gets the file named after it in the fixtures folder, for example
tests/fixtures/fake_ai/test_steps.json for the "test_steps" agent. The answer
is the same whatever documents are attached, but everything around it behaves
as with a real provider: token usage is reported, and an answer longer than
max_tokens comes back truncated, so a too-low limit fails the same way.
"""
from __future__ import annotations

import json
import os
import random
import time
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
        self._calls: dict = {}

    @staticmethod
    def _pause() -> None:
        """KCT_FAKE_DELAY="1-3": wait a random 1 to 3 seconds, like a real model, so loaders can be seen."""
        raw = os.environ.get("KCT_FAKE_DELAY", "").strip()
        if raw:
            low, _, high = raw.partition("-")
            time.sleep(random.uniform(float(low), float(high or low)))

    def prompt(self, request: ProviderRequest) -> ProviderResponse:
        self._pause()
        text = self._answer(request.agent)

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

    def _answer(self, agent: str) -> str:
        """The fixture's text; a fixture that is a JSON list answers its items in turn."""
        text = self._fixture(agent).read_text(encoding="utf-8")
        if text.lstrip().startswith("["):
            items = json.loads(text)
            calls = self._calls.get(agent, 0)
            self._calls[agent] = calls + 1
            return json.dumps(items[calls % len(items)])
        return text

    def _fixture(self, agent: str) -> Path:
        for suffix in (".json", ".md", ".txt"):
            path = self.fixtures / f"{agent}{suffix}"
            if path.is_file():
                return path
        raise AiConfigurationError(f"No fake answer for agent {agent!r} in {self.fixtures}")
