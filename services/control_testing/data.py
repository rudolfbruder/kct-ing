"""Data shapes for control testing (Laravel: Spatie Data objects)."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal

from pydantic import BaseModel


class DocumentKind(str, Enum):
    CONTROL_DETAILS = "control_details"
    TEST_PLAN = "test_plan"

    @property
    def label(self) -> str:
        return {"control_details": "Control details", "test_plan": "Test plan"}[self.value]


Status = Literal["pending", "effective", "not_effective"]


class TestStepDraft(BaseModel):
    """One test step as the agent writes it. The agent never sets the status."""

    id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    refusal_criteria: List[str]


class TestStepList(BaseModel):
    """The test steps agent's output schema."""

    steps: List[TestStepDraft]


class TestStep(TestStepDraft):
    """A stored test step. Stage 3 changes status from pending to the verdict."""

    status: Status = "pending"


class TestStepsResult(BaseModel):
    case_id: str
    summaries: Dict[str, str]
    test_steps: List[TestStep]


class SummaryResult(BaseModel):
    case_id: str
    kind: DocumentKind
    summary: str
