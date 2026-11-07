"""Answers from fixture files instead of a model (KCT_AI_PROVIDER=fake).

Each agent gets the file named after it in the fixtures folder, for example
tests/fixtures/fake_ai/test_steps.json for the "test_steps" agent. The answer
is the same whatever documents are attached, but everything around it behaves
as with a real provider: token usage is reported, and an answer longer than
max_tokens comes back truncated, so a too-low limit fails the same way.
"""
from __future__ import annotations

import json
import re
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

    def prompt(self, request: ProviderRequest) -> ProviderResponse:
        text = self._answer(request.agent, request.prompt)

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

    def _answer(self, agent: str, prompt: str = "") -> str:
        """The fixture's text.

        A JSON list answers its items in turn. A JSON object with "_match" answers the first
        entry whose "regex" is found in the prompt, else "_default": so the fake can answer
        differently per evidence file.
        """
        text = self._fixture(agent).read_text(encoding="utf-8")
        if text.lstrip().startswith("{") and '"_match"' in text:
            rules = json.loads(text)
            for rule in rules["_match"]:
                if re.search(rule["regex"], prompt):
                    return json.dumps(rule["answer"])
            return json.dumps(rules["_default"])
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
