from __future__ import annotations


class AiError(Exception):
    """Base class for every failure while prompting an agent."""


class AiConfigurationError(AiError):
    """The provider is missing configuration, such as a project ID or API key."""


class AiProviderError(AiError):
    """The provider failed or refused to answer."""


class AiOutputTruncatedError(AiError):
    """The answer hit the agent's max_tokens before it was complete."""


class AiInvalidOutputError(AiError):
    """The answer did not match the agent's output schema."""
