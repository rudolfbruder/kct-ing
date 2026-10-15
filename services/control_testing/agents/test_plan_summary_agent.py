from __future__ import annotations

from services.control_testing.agents.summary_agent import SummaryAgent


class TestPlanSummaryAgent(SummaryAgent):
    """Stage 1: test plan PDF(s) to a structured Markdown summary.

    Instructions: prompts/test_plan_summary.md
    """

    name = "test_plan_summary"
