"""API routes bound to controller methods (Laravel: routes/api.php)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter

from controllers.case_interpretations_controller import CaseInterpretationsController
from controllers.cases_controller import CasesController
from controllers.summary_controller import SummaryController
from controllers.test_steps_controller import TestStepsController
from services.control_testing.data import (
    CaseInterpretation,
    CaseInterpretationMetadata,
    SummaryResult,
)
from services.database import manager as database_manager
from services.files.file_service import FileService

files = FileService()
database = database_manager.repository()
cases = CasesController(files)
summaries = SummaryController(files)
test_steps = TestStepsController(files, database)
interpretations = CaseInterpretationsController(database)

router = APIRouter(prefix="/api/v1")

router.add_api_route("/health", cases.health, methods=["GET"])
router.add_api_route("/cases", cases.index, methods=["GET"])
router.add_api_route("/cases/{case_id}/files/{kind}", cases.files_index, methods=["GET"])

# Stage 1
router.add_api_route("/summarize", summaries.store, methods=["POST"], response_model=SummaryResult)

# Stage 2
router.add_api_route("/test-steps", test_steps.store, methods=["POST"], response_model=CaseInterpretation)
router.add_api_route(
    "/cases/{case_id}/test-steps", test_steps.update, methods=["POST"], response_model=CaseInterpretation
)
router.add_api_route(
    "/cases/{case_id}/test-steps", test_steps.show, methods=["GET"], response_model=CaseInterpretation
)
router.add_api_route(
    "/case-interpretations",
    interpretations.index,
    methods=["GET"],
    response_model=List[CaseInterpretationMetadata],
)
router.add_api_route(
    "/case-interpretations/{case_interpretation_id}",
    interpretations.show,
    methods=["GET"],
    response_model=CaseInterpretation,
)
