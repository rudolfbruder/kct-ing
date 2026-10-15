"""Stored case interpretations (Stage 2 runs) and their test steps."""
from __future__ import annotations

from typing import List, Optional

from services.control_testing.data import CaseInterpretation, CaseInterpretationMetadata
from services.database.contracts import CaseInterpretationRepository


class CaseInterpretationsController:
    def __init__(self, database: CaseInterpretationRepository) -> None:
        self.database = database

    def index(self, case_id: Optional[str] = None) -> List[CaseInterpretationMetadata]:
        """GET /case-interpretations?case_id=case-001"""
        return self.database.interpretations(case_id)

    def show(self, case_interpretation_id: str) -> CaseInterpretation:
        """GET /case-interpretations/{case_interpretation_id}"""
        return self.database.find_interpretation(case_interpretation_id)
