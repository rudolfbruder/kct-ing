from __future__ import annotations

from services.control_testing.agents.summary_agent import SummaryAgent


class ControlDetailsSummaryAgent(SummaryAgent):
    """Stage 1: control details PDF(s) to a structured Markdown summary.

    Instructions: prompts/control_details_summary.md
    """

    name = "control_details_summary"
