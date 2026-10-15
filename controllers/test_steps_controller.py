"""Stage 2: from control details + test plan PDFs to test steps."""
from __future__ import annotations

import json
import logging
from typing import List

from fastapi import File, UploadFile

from services.ai.exceptions import AiError
from services.control_testing.agents.control_details_summary_agent import ControlDetailsSummaryAgent
from services.control_testing.agents.test_plan_summary_agent import TestPlanSummaryAgent
from services.control_testing.agents.test_steps_agent import TestStepsAgent
from services.control_testing.data import DocumentKind, TestStep, TestStepsResult
from services.control_testing.exceptions import StageFailedError
from services.files.file_service import FileService, UploadedFile

log = logging.getLogger("kct")

SUMMARIZE = "Summarize the attached document(s)."


class TestStepsController:
    def __init__(self, files: FileService) -> None:
        self.files = files

    def store(
        self,
        control_details: List[UploadFile] = File(...),
        test_plan: List[UploadFile] = File(...),
    ) -> TestStepsResult:
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

    def update(self, case_id: str) -> TestStepsResult:
        """POST /cases/{case_id}/test-steps: (re)generate test steps for a stored case."""
        control_details = self.files.documents(case_id, DocumentKind.CONTROL_DETAILS)
        test_plan = self.files.documents(case_id, DocumentKind.TEST_PLAN)

        try:
            control_summary = ControlDetailsSummaryAgent().prompt(
                SUMMARIZE, attachments=control_details
            ).text
            test_plan_summary = TestPlanSummaryAgent().prompt(SUMMARIZE, attachments=test_plan).text
            drafts = TestStepsAgent().prompt(
                "Produce the test steps.", attachments=control_details + test_plan
            ).structured
        except AiError as exc:
            raise StageFailedError(case_id, exc) from exc

        steps = [TestStep(**draft.model_dump()) for draft in drafts.steps]

        self.files.save_output(case_id, "control_details_summary.md", control_summary)
        self.files.save_output(case_id, "test_plan_summary.md", test_plan_summary)
        self.files.save_output(
            case_id,
            "test_steps.json",
            json.dumps([s.model_dump() for s in steps], indent=2, ensure_ascii=False),
        )
        log.info("%s: generated %d test steps", case_id, len(steps))

        return TestStepsResult(
            case_id=case_id,
            summaries={"control_details": control_summary, "test_plan": test_plan_summary},
            test_steps=steps,
        )

    def show(self, case_id: str) -> List[TestStep]:
        """GET /cases/{case_id}/test-steps: the test steps saved for a case."""
        return [TestStep(**s) for s in json.loads(self.files.read_output(case_id, "test_steps.json"))]


def _read(upload: UploadFile) -> UploadedFile:
    return UploadedFile(name=upload.filename or "", data=upload.file.read())
