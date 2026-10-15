"""One file per agent. Each agent's instructions live in prompts/<agent name>.md."""
from __future__ import annotations

from services.control_testing.agents.control_details_summary_agent import ControlDetailsSummaryAgent
from services.control_testing.agents.summary_agent import SummaryAgent
from services.control_testing.agents.test_plan_summary_agent import TestPlanSummaryAgent
from services.control_testing.agents.test_steps_agent import TestStepsAgent
from services.control_testing.data import DocumentKind

# Which summary agent handles which document kind (used by POST /summarize).
SUMMARY_AGENTS: dict[DocumentKind, type[SummaryAgent]] = {
    DocumentKind.CONTROL_DETAILS: ControlDetailsSummaryAgent,
    DocumentKind.TEST_PLAN: TestPlanSummaryAgent,
}
