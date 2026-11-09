"""Builds the provider an agent asks for (Laravel AI: AiManager).

Providers are imported only when first used, so an environment without the
anthropic package can still run Gemini, and fake mode needs neither SDK.
"""
from __future__ import annotations

from services.ai.exceptions import AiConfigurationError
from services.ai.providers.base import TextProvider
from services.config import Settings, settings

_providers: dict[str, TextProvider] = {}


def provider(name: str, config: Settings | None = None) -> TextProvider:
    if name not in _providers:
        config = config or settings()
        made = _make(name, config)
        if config.ai_record and name not in ("fake", "replay"):
            from services.ai.providers.replay import RecordingProvider

            made = RecordingProvider(made, config.recordings_root / config.ai_record)
        _providers[name] = made
    return _providers[name]


def _make(name: str, config: Settings) -> TextProvider:
    if name == "replay":
        from services.ai.providers.replay import ReplayProvider

        return ReplayProvider(config.recordings_root / config.ai_replay)
    if name == "fake":
        from services.ai.providers.fake import FakeProvider

        return FakeProvider(config.fixtures_root)
    if name == "gemini":
        from services.ai.providers.gemini import GeminiProvider

        return GeminiProvider(config.gcp_project, config.gemini_location)
    if name == "anthropic":
        from services.ai.providers.anthropic import AnthropicProvider

        return AnthropicProvider(
            config.anthropic_platform, config.gcp_project, config.anthropic_region
        )
    raise AiConfigurationError(f"Unknown AI provider {name!r}")
