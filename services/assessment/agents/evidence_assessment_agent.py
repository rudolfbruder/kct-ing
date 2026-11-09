from __future__ import annotations

from services.assessment.data import EvidenceFindings
from services.config import settings
from services.control_testing.agents.prompt_file_agent import PromptFileAgent


class EvidenceAssessmentAgent(PromptFileAgent):
    """Assessment, per evidence part: what this evidence shows for every test step.

    Instructions: prompts/evidence_assessment.md
    Output: EvidenceFindings (services/assessment/data.py)
    """

    name = "evidence_assessment"
    output_schema = EvidenceFindings

    @property
    def max_tokens(self) -> int:
        return settings().assessment_max_tokens
