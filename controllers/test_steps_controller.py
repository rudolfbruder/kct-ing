"""Stage 2: from control details + test plan PDFs to test steps."""
from __future__ import annotations

import logging
from typing import List

from fastapi import File, UploadFile

from services.ai.exceptions import AiError
from services.control_testing.agents.control_details_summary_agent import ControlDetailsSummaryAgent
from services.control_testing.agents.test_plan_summary_agent import TestPlanSummaryAgent
from services.control_testing.agents.test_steps_agent import TestStepsAgent
from services.control_testing.data import CaseInterpretation, DocumentKind
from services.control_testing.exceptions import StageFailedError
from services.database.contracts import CaseInterpretationRepository
from services.files.file_service import FileService, UploadedFile

log = logging.getLogger("kct")

SUMMARIZE = "Summarize the attached document(s)."


class TestStepsController:
    def __init__(self, files: FileService, database: CaseInterpretationRepository) -> None:
        self.files = files
        self.database = database

    def store(
        self,
        control_details: List[UploadFile] = File(...),
        test_plan: List[UploadFile] = File(...),
    ) -> CaseInterpretation:
        """POST /test-steps: store the uploads as a new case, then generate its test steps."""
        case_id = self.files.store_case(
            {
                DocumentKind.CONTROL_DETAILS: [_read(f) for f in control_details],
                DocumentKind.TEST_PLAN: [_read(f) for f in test_plan],
            }
        )
        log.info("%s: stored %d control details and %d test plan file(s)",
                 case_id, len(control_details), len(test_plan))
        return self.update(case_id)

    def update(self, case_id: str) -> CaseInterpretation:
        """POST /cases/{case_id}/test-steps: a new case interpretation of a stored case."""
        control_details = self.files.documents(case_id, DocumentKind.CONTROL_DETAILS)
        test_plan = self.files.documents(case_id, DocumentKind.TEST_PLAN)

        try:
            control_summary = ControlDetailsSummaryAgent().prompt(
                SUMMARIZE, attachments=control_details
            ).text
            test_plan_summary = TestPlanSummaryAgent().prompt(SUMMARIZE, attachments=test_plan).text
            steps = TestStepsAgent().prompt(
                "Produce the test steps.", attachments=control_details + test_plan
            )
        except AiError as exc:
            raise StageFailedError(case_id, exc) from exc

        interpretation = self.database.create_interpretation(
            case_reference=case_id,
            provider=steps.provider,
            model=steps.model,
            summaries={
                DocumentKind.CONTROL_DETAILS.value: control_summary,
                DocumentKind.TEST_PLAN.value: test_plan_summary,
            },
            steps=steps.structured.steps,
        )
        interpretation_id = interpretation.metadata.case_interpretation_id

        self.files.save_output(case_id, "control_details_summary.md", control_summary)
        self.files.save_output(case_id, "test_plan_summary.md", test_plan_summary)
        self.files.save_output(
            case_id,
            f"case_interpretation_{interpretation_id}.json",
            interpretation.model_dump_json(indent=2),
        )
        log.info("%s: case interpretation %s with %d test steps",
                 case_id, interpretation_id, len(interpretation.test_steps))
        return interpretation

    def show(self, case_id: str) -> CaseInterpretation:
        """GET /cases/{case_id}/test-steps: the newest case interpretation of a case."""
        return self.database.latest_interpretation(case_id)


def _read(upload: UploadFile) -> UploadedFile:
    return UploadedFile(name=upload.filename or "", data=upload.file.read())
