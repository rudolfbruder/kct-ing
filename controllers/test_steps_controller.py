"""Interpretation over HTTP (URLs /test-steps). The work is done by InterpretationService."""
from __future__ import annotations

from typing import List

from fastapi import File, UploadFile

from services.control_testing.data import CaseInterpretation
from services.control_testing.interpretation_service import InterpretationService
from services.files.file_service import UploadedFile


class TestStepsController:
    def __init__(self, service: InterpretationService) -> None:
        self.service = service

    def store(
        self,
        control_details: List[UploadFile] = File(...),
        test_plan: List[UploadFile] = File(...),
    ) -> CaseInterpretation:
        """POST /test-steps: store the uploads as a new case, then generate its test steps."""
        return self.service.create_and_generate(
            [_read(f) for f in control_details], [_read(f) for f in test_plan]
        )

    def update(self, case_id: str) -> CaseInterpretation:
        """POST /cases/{case_id}/test-steps: a new case interpretation of a stored case."""
        return self.service.generate(case_id)

    def show(self, case_id: str) -> CaseInterpretation:
        """GET /cases/{case_id}/test-steps: the newest case interpretation of a case."""
        return self.service.latest(case_id)


def _read(upload: UploadFile) -> UploadedFile:
    return UploadedFile(name=upload.filename or "", data=upload.file.read())
