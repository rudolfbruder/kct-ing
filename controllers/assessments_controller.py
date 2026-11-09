"""Assessment over HTTP. Runs in the background; the work is done by AssessmentService."""
from __future__ import annotations

from typing import List, Optional

from fastapi import BackgroundTasks, Body
from fastapi.responses import Response
from pydantic import BaseModel

from services.assessment.assessment_service import AssessmentService
from services.assessment.data import Assessment, AssessmentMetadata


class StartAssessmentRequest(BaseModel):
    # Default: the case's newest interpretation.
    case_interpretation_id: Optional[str] = None


class AssessmentsController:
    def __init__(self, service: AssessmentService) -> None:
        self.service = service

    def store(
        self,
        case_id: str,
        background: BackgroundTasks,
        payload: Optional[StartAssessmentRequest] = Body(None),
    ) -> AssessmentMetadata:
        """POST /cases/{case_id}/assessments: start a run; returns at once with its ID (status queued)."""
        metadata = self.service.start(case_id, payload.case_interpretation_id if payload else None)
        background.add_task(self.service.run, metadata.assessment_id)
        return metadata

    def index(self, case_id: str) -> List[AssessmentMetadata]:
        """GET /cases/{case_id}/assessments: every run of the case, newest first."""
        return self.service.index(case_id)

    def show(self, assessment_id: str) -> Assessment:
        """GET /assessments/{assessment_id}: progress while running; verdicts and findings when done."""
        return self.service.find(assessment_id)

    def report(self, assessment_id: str) -> Response:
        """GET /assessments/{assessment_id}/report.pdf: the read-only PDF of a completed run."""
        data = self.service.report(assessment_id)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="assessment_{assessment_id}.pdf"'})
