"""Part of the interpretation: summarize one document kind of a stored case.

    kct.summaries.summarize("case-001", DocumentKind.TEST_PLAN)
"""
from __future__ import annotations

from services.ai.exceptions import AiError
from services.control_testing.agents import SUMMARY_AGENTS
from services.control_testing.data import DocumentKind, SummaryResult
from services.control_testing.exceptions import InterpretationFailedError
from services.files.file_service import FileService


class SummaryService:
    def __init__(self, files: FileService) -> None:
        self.files = files

    def summarize(self, case_id: str, kind: DocumentKind) -> SummaryResult:
        documents = self.files.documents(case_id, kind)
        try:
            summary = SUMMARY_AGENTS[kind]().prompt(
                "Summarize the attached document(s).", attachments=documents
            ).text
        except AiError as exc:
            raise InterpretationFailedError(case_id, exc) from exc

        self.files.save_output(case_id, f"{kind.value}_summary.md", summary)
        return SummaryResult(case_id=case_id, kind=kind, summary=summary)
