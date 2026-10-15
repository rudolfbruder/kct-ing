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
    """One test step as the agent writes it. The database assigns the ID and status."""

    # Step ID from the test plan (0472-01), or DERIVED-01... for gaps the agent filled.
    reference: str
    title: str
    description: str
    acceptance_criteria: List[str]
    refusal_criteria: List[str]


class TestStepList(BaseModel):
    """The test steps agent's output schema."""

    steps: List[TestStepDraft]


class TestStep(BaseModel):
    """A stored test step. Stage 3 changes status from pending to the verdict."""

    # IDs are UUIDs made when the row is saved, the same on every database driver.
    id: str
    case_interpretation_id: str
    case_id: str
    reference: str
    title: str
    description: str
    acceptance_criteria: List[str]
    refusal_criteria: List[str]
    status: Status = "pending"


class CaseInterpretationMetadata(BaseModel):
    """Header of one Stage 2 run over a case."""

    case_interpretation_id: str
    case_id: str
    # Folder name of the case under storage/uploads, e.g. case-001.
    case_reference: str
    provider: str
    model: str
    created_at: str
    step_count: int


class CaseInterpretation(BaseModel):
    """One Stage 2 run: its metadata, the two summaries and the test steps."""

    metadata: CaseInterpretationMetadata
    summaries: Dict[str, str]
    test_steps: List[TestStep]


class SummaryResult(BaseModel):
    case_id: str
    kind: DocumentKind
    summary: str
