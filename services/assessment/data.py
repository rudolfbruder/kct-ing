"""Data of the assessment: what the agents answer, and what is stored.

Agents answer in the *schema* models (EvidenceFindings, VerdictList); test steps are
named by their reference (0472-04), which models handle more reliably than UUIDs.
The service turns answers into the *stored* models (AssessedPart, StepVerdict).
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Relevance = Literal["supports", "contradicts", "partly", "not_relevant"]
CriterionStatus = Literal["met", "not_met", "not_shown"]
Verdict = Literal["effective", "not_effective"]
AssessmentStatus = Literal["queued", "running", "completed", "failed"]


# --- agent answers (JSON schemas sent to the model) ------------------------------------

class Reference(BaseModel):
    """Where in the evidence something is shown."""

    document: str = Field(description="Exact title of the evidence document as given in the prompt")
    location: str = Field("", description='e.g. "page 12", "Sheet \\"Reset events\\" row 14, column K", '
                                          '"email body, earlier email 2"')


class CriterionCheck(BaseModel):
    criterion: str = Field(description="The criterion, copied from the test step")
    kind: Literal["acceptance", "refusal"]
    status: CriterionStatus
    reference: Optional[Reference] = None
    quote: str = Field("", description="Short quote or value from the evidence that shows it")


class ExceptionItem(BaseModel):
    """One sampled item that fails, e.g. one ticket."""

    item: str = Field(description="The item's ID, e.g. a ticket number")
    description: str
    reference: Optional[Reference] = None


class StepFinding(BaseModel):
    step_reference: str = Field(description="The test step's reference, e.g. 0472-04")
    relevance: Relevance
    criteria: List[CriterionCheck] = []
    exceptions: List[ExceptionItem] = []
    summary: str = Field("", description="One or two sentences on what this evidence shows for the step")


class EvidenceFindings(BaseModel):
    """Answer of the evidence assessment agent for one evidence part."""

    findings: List[StepFinding]


class StepVerdictAnswer(BaseModel):
    step_reference: str
    verdict: Verdict
    no_evidence: bool = Field(description="True when no evidence says anything about this step")
    reason: str
    exceptions: List[ExceptionItem] = []
    references: List[Reference] = []


class VerdictList(BaseModel):
    """Answer of the verdict agent: one verdict per test step."""

    verdicts: List[StepVerdictAnswer]


# --- stored -------------------------------------------------------------------------

class CheckedStepFinding(StepFinding):
    # References that do not match the evidence sent (wrong document, page outside the part, ...).
    reference_problems: List[str] = []


class AssessedPart(BaseModel):
    """One evidence part sent to the model, and what came back."""

    id: str
    position: int
    unit: str                       # the evidence file, relative to the case's evidence folder
    unit_sha256: str
    part_number: int
    part_total: int
    label: str
    documents: List[str]
    estimated_tokens: int
    status: Literal["assessed", "failed"]
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    findings: List[CheckedStepFinding] = []


class StepVerdict(BaseModel):
    id: str
    test_step_id: str
    step_reference: str
    title: str
    verdict: Verdict
    no_evidence: bool
    reason: str
    exceptions: List[ExceptionItem] = []
    references: List[Reference] = []
    fallback: bool = False          # made by the code because the model gave no verdict for the step
    reference_problems: List[str] = []   # references that match no evidence document sent


class AssessmentMetadata(BaseModel):
    assessment_id: str
    case_id: str
    case_reference: str
    case_interpretation_id: str
    status: AssessmentStatus
    provider: str
    model: str
    parts_total: int = 0
    parts_done: int = 0
    parts_failed: int = 0
    created_at: str
    finished_at: Optional[str] = None
    error: Optional[str] = None
    report_path: Optional[str] = None
    report_sha256: Optional[str] = None
    # Run figures (set when completed)
    evidence_files: int = 0
    duration_seconds: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: Optional[float] = None    # only with KCT_PRICE_* set; in KCT_PRICE_CURRENCY


class Assessment(BaseModel):
    metadata: AssessmentMetadata
    parts: List[AssessedPart] = []
    verdicts: List[StepVerdict] = []
