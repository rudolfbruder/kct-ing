"""API routes bound to controller methods (Laravel: routes/api.php)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter

from controllers.cases_controller import CasesController
from controllers.summary_controller import SummaryController
from controllers.test_steps_controller import TestStepsController
from services.control_testing.data import SummaryResult, TestStep, TestStepsResult
from services.files.file_service import FileService

files = FileService()
cases = CasesController(files)
summaries = SummaryController(files)
test_steps = TestStepsController(files)

router = APIRouter(prefix="/api/v1")

router.add_api_route("/health", cases.health, methods=["GET"])
router.add_api_route("/cases", cases.index, methods=["GET"])
router.add_api_route("/cases/{case_id}/files/{kind}", cases.files_index, methods=["GET"])

# Stage 1
router.add_api_route("/summarize", summaries.store, methods=["POST"], response_model=SummaryResult)

# Stage 2
router.add_api_route("/test-steps", test_steps.store, methods=["POST"], response_model=TestStepsResult)
router.add_api_route(
    "/cases/{case_id}/test-steps", test_steps.update, methods=["POST"], response_model=TestStepsResult
)
router.add_api_route(
    "/cases/{case_id}/test-steps", test_steps.show, methods=["GET"], response_model=List[TestStep]
)
