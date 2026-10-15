"""Base class for agents (Laravel AI: Contracts\\Agent + Promptable).

An agent is one job for a model: its instructions, its limits and, when the
answer must be structured, the output schema. Subclasses set class attributes
the way Laravel agents use #[MaxTokens] / #[Temperature] / #[Provider]:

    class TestStepsAgent(Agent):
        name = "test_steps"
        max_tokens = 32768
        output_schema = TestStepList

        def instructions(self) -> str:
            return "You are..."

    response = TestStepsAgent().prompt("Produce the test steps.", attachments=[...])
    response.structured  # a validated TestStepList

provider and model default to KCT_AI_PROVIDER / KCT_AI_MODEL; an agent can
pin its own, and a single call can override both.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import time
import uuid
from typing import ClassVar, Optional

from pydantic import BaseModel, ValidationError

from services.ai import manager
from services.ai.attachments import Document
from services.ai.exceptions import AiInvalidOutputError, AiOutputTruncatedError
from services.ai.providers.base import ProviderRequest
from services.ai.responses import AgentResponse, ProviderResponse, Usage
from services.config import DEFAULT_MODELS, settings

log = logging.getLogger("kct.ai")
calls_log = logging.getLogger("kct.ai.calls")


class Agent:
    name: ClassVar[str] = "agent"
    provider: ClassVar[Optional[str]] = None
    model: ClassVar[Optional[str]] = None
    # Plain attribute, so a subclass can make it a property that reads settings.
    max_tokens: int = 16384
    temperature: ClassVar[Optional[float]] = None
    output_schema: ClassVar[Optional[type[BaseModel]]] = None

    # Set by fake(); answers are handed out in order instead of calling a provider.
    _fake_answers: ClassVar[Optional[list[str]]] = None

    def instructions(self) -> str:
        raise NotImplementedError

    def prompt(
        self,
        text: str,
        attachments: Optional[list[Document]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AgentResponse:
        config = settings()
        provider_name = provider or self.provider or config.ai_provider
        model_name = model or self.model or self._default_model(provider_name)
        request = ProviderRequest(
            agent=self.name,
            instructions=self.instructions(),
            prompt=text,
            attachments=attachments or [],
            model=model_name,
            max_tokens=self.max_tokens,
            temperature=config.temperature if self.temperature is None else self.temperature,
            output_schema=self.output_schema,
        )

        invocation_id = str(uuid.uuid4())
        started = time.monotonic()
        raw = self._call(provider_name, request)
        duration_ms = int((time.monotonic() - started) * 1000)

        response = AgentResponse(
            # Models sometimes wrap the whole answer in a ``` fence; it is never part of the answer.
            text=_strip_code_fence(raw.text),
            invocation_id=invocation_id,
            agent=self.name,
            provider=provider_name,
            model=raw.model,
            usage=raw.usage,
            duration_ms=duration_ms,
        )
        self._log(response, request, raw.truncated)

        if raw.truncated:
            raise AiOutputTruncatedError(
                f"{self.name}: answer hit max_tokens={self.max_tokens} "
                f"(invocation {invocation_id}). Raise the agent's max_tokens."
            )
        if self.output_schema is None:
            return response

        try:
            structured = self.output_schema.model_validate_json(response.text)
        except ValidationError as exc:
            raise AiInvalidOutputError(
                f"{self.name}: answer does not match {self.output_schema.__name__} "
                f"(invocation {invocation_id}): {exc}"
            ) from exc
        return dataclasses.replace(response, structured=structured)

    @classmethod
    def fake(cls, answers: list[str]) -> None:
        """Answer the next prompts with these texts, in order (Laravel: Agent::fake())."""
        cls._fake_answers = list(answers)

    @classmethod
    def stop_faking(cls) -> None:
        cls._fake_answers = None

    def _call(self, provider_name: str, request: ProviderRequest) -> ProviderResponse:
        answers = type(self)._fake_answers
        if answers is not None:
            if not answers:
                raise AssertionError(f"{self.name}: no fake answers left")
            return ProviderResponse(text=answers.pop(0), model="faked", usage=Usage())
        return manager.provider(provider_name).prompt(request)

    @staticmethod
    def _default_model(provider_name: str) -> str:
        config = settings()
        if provider_name == config.ai_provider:
            return config.ai_model
        return DEFAULT_MODELS[provider_name]

    @staticmethod
    def _log(response: AgentResponse, request: ProviderRequest, truncated: bool) -> None:
        log.info(
            "%s via %s/%s: %d in / %d out tokens, %d ms%s (invocation %s)",
            response.agent, response.provider, response.model,
            response.usage.input_tokens, response.usage.output_tokens, response.duration_ms,
            ", TRUNCATED" if truncated else "", response.invocation_id,
        )
        calls_log.info(
            json.dumps(
                {
                    "invocation_id": response.invocation_id,
                    "agent": response.agent,
                    "provider": response.provider,
                    "model": response.model,
                    "attachments": [doc.title for doc in request.attachments],
                    "max_tokens": request.max_tokens,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "duration_ms": response.duration_ms,
                    "truncated": truncated,
                    "output": response.text,
                },
                ensure_ascii=False,
            )
        )


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text
