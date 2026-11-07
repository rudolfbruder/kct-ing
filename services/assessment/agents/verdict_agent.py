from __future__ import annotations

from services.assessment.data import VerdictList
from services.config import settings
from services.control_testing.agents.prompt_file_agent import PromptFileAgent


class VerdictAgent(PromptFileAgent):
    """Assessment, once per run: the findings of all evidence parts into one verdict per test step.

    Instructions: prompts/evidence_verdict.md
    Output: VerdictList (services/assessment/data.py)
    """

    name = "evidence_verdict"
    output_schema = VerdictList

    @property
    def max_tokens(self) -> int:
        return settings().verdict_max_tokens
