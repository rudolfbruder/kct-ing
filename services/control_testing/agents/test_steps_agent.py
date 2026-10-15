from __future__ import annotations

from services.config import settings
from services.control_testing.agents.prompt_file_agent import PromptFileAgent
from services.control_testing.data import TestStepList


class TestStepsAgent(PromptFileAgent):
    """Stage 2: control details + test plan PDFs to test steps for Stage 3.

    Instructions: prompts/test_steps.md
    Output: TestStepList (services/control_testing/data.py)
    """

    name = "test_steps"
    output_schema = TestStepList

    @property
    def max_tokens(self) -> int:
        # A step list is much longer than a summary, so this has its own limit.
        return settings().steps_max_tokens
