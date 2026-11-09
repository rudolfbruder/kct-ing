"""What every database driver must offer (Laravel: a repository interface).

Controllers and scripts depend on this contract only, so switching from
SQLite to BigQuery (or anything else) is a setting, not a change to callers.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from services.assessment.data import Assessment, AssessedPart, AssessmentMetadata, StepVerdict
from services.control_testing.data import (
    CaseInterpretation,
    CaseInterpretationMetadata,
    TestStepDraft,
)


class CaseInterpretationRepository(Protocol):
    def create_interpretation(
        self,
        case_reference: str,
        provider: str,
        model: str,
        summaries: Dict[str, str],
        steps: List[TestStepDraft],
    ) -> CaseInterpretation:
        """Saves one interpretation run and its test steps in a single transaction.

        Creates the case row on first use. Returns the run with database IDs.
        """
        ...

    def find_interpretation(self, case_interpretation_id: str) -> CaseInterpretation:
        """Raises RecordNotFoundError when there is no such interpretation."""
        ...

    def latest_interpretation(self, case_reference: str) -> CaseInterpretation:
        """The newest interpretation of a case. Raises RecordNotFoundError when there is none."""
        ...

    def interpretations(self, case_reference: Optional[str] = None) -> List[CaseInterpretationMetadata]:
        """Metadata of every interpretation, newest first, optionally for one case."""
        ...


class AssessmentRepository(Protocol):
    """Assessment runs, the evidence parts they sent, and the verdicts. Same on every driver."""

    def create_assessment(self, metadata: "AssessmentMetadata") -> None:
        ...

    def update_assessment(self, assessment_id: str, **fields) -> None:
        """Change metadata fields (status, parts_done, finished_at, error, report_path, ...)."""
        ...

    def save_part(self, assessment_id: str, part: "AssessedPart") -> None:
        ...

    def save_verdicts(self, assessment_id: str, verdicts: List["StepVerdict"]) -> None:
        """Store the verdicts and set each test step's status to its verdict."""
        ...

    def find_assessment(self, assessment_id: str) -> "Assessment":
        """Raises RecordNotFoundError when there is no such assessment."""
        ...

    def assessments(self, case_reference: Optional[str] = None) -> List["AssessmentMetadata"]:
        """Metadata of every assessment, newest first, optionally for one case."""
        ...
