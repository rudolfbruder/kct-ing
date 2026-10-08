"""Schemas. Laravel analogy: Form Requests + DTOs + an Eloquent-ish shape for
what we persist. Pydantic validates on the way in and on the way out.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DocumentKind(str, Enum):
    CONTROL_DETAILS = "control_details"
    TEST_PLAN = "test_plan"
    EVIDENCE = "evidence"


class SourceFile(BaseModel):
    """One input file, recorded so a run can be reproduced and audited."""

    filename: str
    relative_path: str
    mime_type: str
    size_bytes: int
    sha256: str


class CaseManifest(BaseModel):
    """storage/cases/<case_id>/case.json — what this case is about."""

    case_id: str
    process_id: str | None = None
    process_name: str | None = None
    testing_period: str | None = None
    source: str = "manual-upload"
    created_at: datetime
    notes: str | None = None


class SummarizeRequest(BaseModel):
    kind: DocumentKind
    prompt_version: str | None = Field(
        default=None, description="Pin a prompt version; defaults to the latest on disk."
    )
    force: bool = Field(
        default=False, description="Re-run even if a summary already exists."
    )


class RunRecord(BaseModel):
    """The audit trail for a single model call. Written next to every output.

    Model risk management wants: who/what ran, against which inputs, with which
    prompt and model version, and when. All of it is in here.
    """

    run_id: str
    case_id: str
    stage: Literal["summarize"] = "summarize"
    kind: DocumentKind
    model: str
    location: str
    temperature: float
    prompt_name: str
    prompt_version: str
    prompt_sha256: str
    inputs: list[SourceFile]
    output_path: str
    output_sha256: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    usage: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class SummarizeResponse(BaseModel):
    run_id: str
    case_id: str
    kind: DocumentKind
    output_path: str
    summary: str
    prompt_version: str
    model: str
