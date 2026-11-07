"""One summary over HTTP (part of the interpretation). The work is done by SummaryService."""
from __future__ import annotations

from pydantic import BaseModel

from services.control_testing.data import DocumentKind, SummaryResult
from services.control_testing.summary_service import SummaryService


class SummarizeRequest(BaseModel):
    case_id: str = "case-001"
    kind: DocumentKind = DocumentKind.CONTROL_DETAILS


class SummaryController:
    def __init__(self, service: SummaryService) -> None:
        self.service = service

    def store(self, payload: SummarizeRequest) -> SummaryResult:
        """POST /summarize"""
        return self.service.summarize(payload.case_id, payload.kind)
