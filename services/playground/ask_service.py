"""Smallest possible round trip through the AI layer: ask a question, get text back.

Use it to check that the configured provider works before a real interpretation or assessment:

    kct.ask.ask("What is 5+2?")       # notebook
    POST /api/v1/ask {"question": "What is 5+2?"}   # API

In fake mode the answer comes from tests/fixtures/fake_ai/ask.md, whatever
the question.
"""
from __future__ import annotations

from pydantic import BaseModel

from services.ai.agent import Agent


class AskAgent(Agent):
    name = "ask"
    max_tokens = 1024

    def instructions(self) -> str:
        return "Answer the question in one short sentence."


class AskResult(BaseModel):
    question: str
    answer: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class AskService:
    def ask(self, question: str) -> AskResult:
        response = AskAgent().prompt(question)
        return AskResult(
            question=question,
            answer=response.text,
            provider=response.provider,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            duration_ms=response.duration_ms,
        )
