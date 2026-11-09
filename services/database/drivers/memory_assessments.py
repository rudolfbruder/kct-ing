"""Assessment storage for the memory driver: kept in the process, gone after a restart."""
from __future__ import annotations

import threading
from typing import Dict, List, Optional

from services.assessment.data import Assessment, AssessedPart, AssessmentMetadata, StepVerdict
from services.database.exceptions import RecordNotFoundError


class MemoryAssessments:
    def _assessment_store(self) -> Dict[str, Assessment]:
        if not hasattr(self, "_assessments_by_id"):
            self._assessments_by_id: Dict[str, Assessment] = {}
            self._assessments_lock = threading.Lock()
        return self._assessments_by_id

    def create_assessment(self, metadata: AssessmentMetadata) -> None:
        store = self._assessment_store()
        with self._assessments_lock:
            store[metadata.assessment_id] = Assessment(metadata=metadata.model_copy())

    def update_assessment(self, assessment_id: str, **fields) -> None:
        item = self._get(assessment_id)
        with self._assessments_lock:
            item.metadata = item.metadata.model_copy(update=fields)

    def save_part(self, assessment_id: str, part: AssessedPart) -> None:
        item = self._get(assessment_id)
        with self._assessments_lock:
            item.parts.append(part.model_copy(deep=True))

    def save_verdicts(self, assessment_id: str, verdicts: List[StepVerdict]) -> None:
        item = self._get(assessment_id)
        status = {v.test_step_id: v.verdict for v in verdicts}
        with self._assessments_lock:
            item.verdicts = [v.model_copy(deep=True) for v in verdicts]
            for interpretation in getattr(self, "_interpretations", []):
                for step in interpretation.test_steps:
                    if step.id in status:
                        step.status = status[step.id]

    def find_assessment(self, assessment_id: str) -> Assessment:
        return self._get(assessment_id).model_copy(deep=True)

    def assessments(self, case_reference: Optional[str] = None) -> List[AssessmentMetadata]:
        items = [a.metadata for a in self._assessment_store().values()
                 if case_reference is None or a.metadata.case_reference == case_reference]
        return [m.model_copy() for m in sorted(items, key=lambda m: m.created_at, reverse=True)]

    def _get(self, assessment_id: str) -> Assessment:
        item = self._assessment_store().get(assessment_id)
        if item is None:
            raise RecordNotFoundError(f"No assessment {assessment_id}")
        return item
