"""The strategy every provider implements (Laravel AI: Contracts\\Providers\\TextProvider)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from pydantic import BaseModel

from services.ai.attachments import Document
from services.ai.responses import ProviderResponse


@dataclass(frozen=True)
class ProviderRequest:
    agent: str  # agent name, e.g. "test_steps"; the fake provider picks its fixture by it
    instructions: str
    prompt: str
    attachments: list[Document]
    model: str
    max_tokens: int
    temperature: float
    # When set, the provider constrains the answer to this model's JSON schema.
    output_schema: Optional[type[BaseModel]] = None


class TextProvider(Protocol):
    name: str

    def prompt(self, request: ProviderRequest) -> ProviderResponse: ...
