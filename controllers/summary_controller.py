"""Stage 1: summarize one document kind of a stored case."""
from __future__ import annotations

from pydantic import BaseModel

from services.ai.exceptions import AiError
from services.control_testing.agents import SUMMARY_AGENTS
from services.control_testing.data import DocumentKind, SummaryResult
from services.control_testing.exceptions import StageFailedError
from services.files.file_service import FileService


class SummarizeRequest(BaseModel):
    case_id: str = "case-001"
    kind: DocumentKind = DocumentKind.CONTROL_DETAILS


class SummaryController:
    def __init__(self, files: FileService) -> None:
        self.files = files

    def store(self, payload: SummarizeRequest) -> SummaryResult:
        """POST /summarize"""
        documents = self.files.documents(payload.case_id, payload.kind)
        try:
            summary = SUMMARY_AGENTS[payload.kind]().prompt(
                "Summarize the attached document(s).", attachments=documents
            ).text
        except AiError as exc:
            raise StageFailedError(payload.case_id, exc) from exc

        self.files.save_output(payload.case_id, f"{payload.kind.value}_summary.md", summary)
        return SummaryResult(case_id=payload.case_id, kind=payload.kind, summary=summary)
