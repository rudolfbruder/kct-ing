"""Interpretation: from control details + test plan PDFs to summaries and test steps.

Used by the API (controllers/test_steps_controller.py) and directly from
notebooks:

    from services.app import boot
    kct = boot()
    case_id = kct.interpretations.create_case(["CD.pdf"], ["TP.pdf"])
    interpretation = kct.interpretations.generate(case_id)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Union

from services.ai.exceptions import AiError
from services.control_testing.agents.control_details_summary_agent import ControlDetailsSummaryAgent
from services.control_testing.agents.test_plan_summary_agent import TestPlanSummaryAgent
from services.control_testing.agents.test_steps_agent import TestStepsAgent
from services.control_testing.data import CaseInterpretation, DocumentKind
from services.control_testing.exceptions import InterpretationFailedError
from services.database.contracts import CaseInterpretationRepository
from services.files.file_service import FileService, UploadedFile

log = logging.getLogger("kct")

SUMMARIZE = "Summarize the attached document(s)."

# A notebook can pass file paths; the API passes UploadedFile objects.
FileInput = Union[UploadedFile, str, Path]


class InterpretationService:
    def __init__(self, files: FileService, database: CaseInterpretationRepository) -> None:
        self.files = files
        self.database = database

    def create_case(
        self, control_details: Iterable[FileInput], test_plan: Iterable[FileInput]
    ) -> str:
        """Store the documents as a new case and return its ID (case-001, ...)."""
        control = [_as_upload(f) for f in control_details]
        plan = [_as_upload(f) for f in test_plan]
        case_id = self.files.store_case(
            {DocumentKind.CONTROL_DETAILS: control, DocumentKind.TEST_PLAN: plan}
        )
        log.info("%s: stored %d control details and %d test plan file(s)",
                 case_id, len(control), len(plan))
        return case_id

    def generate(self, case_id: str) -> CaseInterpretation:
        """Run the three agents on a stored case and save a new case interpretation."""
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
            raise InterpretationFailedError(case_id, exc) from exc

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

    def create_and_generate(
        self, control_details: Iterable[FileInput], test_plan: Iterable[FileInput]
    ) -> CaseInterpretation:
        return self.generate(self.create_case(control_details, test_plan))

    def latest(self, case_id: str) -> CaseInterpretation:
        """The newest case interpretation of a case."""
        return self.database.latest_interpretation(case_id)


def _as_upload(file: FileInput) -> UploadedFile:
    if isinstance(file, UploadedFile):
        return file
    path = Path(file)
    return UploadedFile(name=path.name, data=path.read_bytes())
