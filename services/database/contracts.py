"""What every database driver must offer (Laravel: a repository interface).

Controllers and scripts depend on this contract only, so switching from
SQLite to BigQuery (or anything else) is a setting, not a change to callers.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Protocol

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
        """Saves one Stage 2 run and its test steps in a single transaction.

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
