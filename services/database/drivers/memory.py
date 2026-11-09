"""Memory driver (KCT_DB_DRIVER=memory, the default): nothing is written anywhere.

Case interpretations live in this Python process only and are gone after a
restart (uvicorn reload, notebook kernel restart). Use it until a database is
approved; the readable copies in outputs/case-NNN/ are still written by the
file service. Behaves like the SQLite and BigQuery drivers otherwise: UUIDs,
newest first, RecordNotFoundError for unknown IDs.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from services.control_testing.data import (
    CaseInterpretation,
    CaseInterpretationMetadata,
    TestStep,
    TestStepDraft,
)
from services.database.drivers.memory_assessments import MemoryAssessments
from services.database.exceptions import RecordNotFoundError


class MemoryRepository(MemoryAssessments):
    def __init__(self) -> None:
        self._cases: Dict[str, str] = {}  # case reference -> case UUID
        self._interpretations: List[CaseInterpretation] = []  # oldest first
        self._lock = threading.Lock()

    def create_interpretation(
        self,
        case_reference: str,
        provider: str,
        model: str,
        summaries: Dict[str, str],
        steps: List[TestStepDraft],
    ) -> CaseInterpretation:
        with self._lock:
            case_id = self._cases.setdefault(case_reference, str(uuid.uuid4()))
            interpretation_id = str(uuid.uuid4())
            interpretation = CaseInterpretation(
                metadata=CaseInterpretationMetadata(
                    case_interpretation_id=interpretation_id,
                    case_id=case_id,
                    case_reference=case_reference,
                    provider=provider,
                    model=model,
                    created_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    step_count=len(steps),
                ),
                summaries=dict(summaries),
                test_steps=[
                    TestStep(
                        id=str(uuid.uuid4()),
                        case_interpretation_id=interpretation_id,
                        case_id=case_id,
                        **step.model_dump(),
                    )
                    for step in steps
                ],
            )
            self._interpretations.append(interpretation)
        return interpretation.model_copy(deep=True)

    def find_interpretation(self, case_interpretation_id: str) -> CaseInterpretation:
        for interpretation in self._interpretations:
            if interpretation.metadata.case_interpretation_id == case_interpretation_id:
                return interpretation.model_copy(deep=True)
        raise RecordNotFoundError(f"No case interpretation {case_interpretation_id}")

    def latest_interpretation(self, case_reference: str) -> CaseInterpretation:
        latest = self.interpretations(case_reference)
        if not latest:
            raise RecordNotFoundError(f"No case interpretation for {case_reference}")
        return self.find_interpretation(latest[0].case_interpretation_id)

    def interpretations(self, case_reference: Optional[str] = None) -> List[CaseInterpretationMetadata]:
        return [
            i.metadata.model_copy()
            for i in reversed(self._interpretations)
            if case_reference is None or i.metadata.case_reference == case_reference
        ]
