from __future__ import annotations

from services.config import settings
from services.control_testing.agents.prompt_file_agent import PromptFileAgent


class SummaryAgent(PromptFileAgent):
    """Shared by the interpretation's summary agents: same token limit, plain Markdown output."""

    @property
    def max_tokens(self) -> int:
        return settings().summary_max_tokens
