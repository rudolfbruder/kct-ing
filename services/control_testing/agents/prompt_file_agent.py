from __future__ import annotations

from services.ai.agent import Agent
from services.config import settings


class PromptFileAgent(Agent):
    """An agent whose instructions are the file prompts/<name>.md."""

    def instructions(self) -> str:
        return (settings().prompts_root / f"{self.name}.md").read_text(encoding="utf-8")
