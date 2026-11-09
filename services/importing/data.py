"""Data of a control folder import."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DocumentRole = Literal["control_details", "test_plan", "evidence", "other"]


class DocumentChoice(BaseModel):
    """Answer of the document classifier: the one control details and the one test plan."""

    control_details: str = Field(description="Path of the control details file, exactly as listed")
    test_plan: str = Field(description="Path of the test plan file, exactly as listed")
    reason: str = Field(description="One or two sentences: what in the two files decided it")


class ClassifiedFile(BaseModel):
    name: str
    role: DocumentRole
    reason: str
    by: Literal["ai", "override"] = "ai"


class SkippedFile(BaseModel):
    path: str
    reason: str


class ImportResult(BaseModel):
    case_id: str
    case_name: str
    source: str
    control_details: List[ClassifiedFile]
    test_plan: List[ClassifiedFile]
    other: List[ClassifiedFile] = []
    evidence: List[str] = []                 # paths in the case's evidence folder
    skipped: List[SkippedFile] = []
    removed_evidence: List[str] = []         # earlier evidence no longer in the folder, removed from the case
    case_interpretation_id: Optional[str] = None
    assessment_id: Optional[str] = None
    # ZIP imports only
    source_zip: Optional[str] = None         # the uploaded ZIP, kept under storage/imports/<case>/source/
    sorted_folder: Optional[str] = None      # storage/imports/<case>/ in the SharePoint structure
    sorted_by_ai: List[ClassifiedFile] = []  # flat ZIPs: every file's role, decided by the AI
