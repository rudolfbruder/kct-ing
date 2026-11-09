"""API routes bound to controller methods (Laravel: routes/api.php)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter

from controllers.ask_controller import AskController
from controllers.assessments_controller import AssessmentsController
from controllers.case_interpretations_controller import CaseInterpretationsController
from controllers.cases_controller import CasesController
from controllers.imports_controller import ImportsController
from controllers.evidences_controller import (
    EvidenceFileModel,
    EvidencePartModel,
    EvidencesController,
    EvidenceUploadResult,
)
from controllers.summary_controller import SummaryController
from controllers.test_steps_controller import TestStepsController
from services.app import boot
from services.control_testing.data import (
    CaseInterpretation,
    CaseInterpretationMetadata,
    SummaryResult,
)
from services.assessment.data import Assessment, AssessmentMetadata
from services.importing.data import ImportResult
from services.playground.ask_service import AskResult

kct = boot()
cases = CasesController(kct.files)
summaries = SummaryController(kct.summaries)
test_steps = TestStepsController(kct.interpretations)
interpretations = CaseInterpretationsController(kct.database)
ask = AskController(kct.ask)
evidences = EvidencesController(kct.files, kct.evidences)
assessments = AssessmentsController(kct.assessments)
imports = ImportsController(kct.importer, kct.assessments)

router = APIRouter(prefix="/api/v1")

router.add_api_route("/health", cases.health, methods=["GET"])
router.add_api_route("/ask", ask.store, methods=["POST"], response_model=AskResult)
router.add_api_route("/cases", cases.index, methods=["GET"])
router.add_api_route("/cases/import", imports.store, methods=["POST"], response_model=ImportResult)
router.add_api_route("/cases/import-zip", imports.store_zip, methods=["POST"], response_model=ImportResult)
router.add_api_route("/cases/{case_id}/files/{kind}", cases.files_index, methods=["GET"])

# Interpretation: one summary (part of the interpretation)
router.add_api_route("/summarize", summaries.store, methods=["POST"], response_model=SummaryResult)

# Interpretation: summaries + test steps
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

# Evidence of a case
router.add_api_route(
    "/cases/{case_id}/evidences", evidences.store, methods=["POST"], response_model=EvidenceUploadResult
)
router.add_api_route(
    "/cases/{case_id}/evidences", evidences.index, methods=["GET"], response_model=List[EvidenceFileModel]
)
router.add_api_route(
    "/cases/{case_id}/evidences/parts", evidences.parts, methods=["GET"], response_model=List[EvidencePartModel]
)

# Assessment: runs in the background
router.add_api_route(
    "/cases/{case_id}/assessments", assessments.store, methods=["POST"], response_model=AssessmentMetadata,
    status_code=202,
)
router.add_api_route(
    "/cases/{case_id}/assessments", assessments.index, methods=["GET"], response_model=List[AssessmentMetadata]
)
router.add_api_route("/assessments/{assessment_id}", assessments.show, methods=["GET"], response_model=Assessment)
router.add_api_route("/assessments/{assessment_id}/report.pdf", assessments.report, methods=["GET"])
