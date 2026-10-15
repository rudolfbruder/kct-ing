"""What providers return and what agents hand back (Laravel AI: Responses\\*)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ProviderResponse:
    """Raw answer from a provider, before the agent validates it."""

    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    # True when the provider stopped because it hit max_tokens.
    truncated: bool = False


@dataclass(frozen=True)
class AgentResponse:
    """What agent.prompt() returns."""

    text: str
    invocation_id: str
    agent: str
    provider: str
    model: str
    usage: Usage
    duration_ms: int
    # The validated output model, when the agent declares an output schema.
    structured: Optional[Any] = None
