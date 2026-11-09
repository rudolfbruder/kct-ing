"""Checks the references a model gives against the evidence it was sent.

Models sometimes cite a document, page or row that does not exist. Every
reference in a finding is checked; problems are stored with the finding
(`reference_problems`) and shown in the report, never silently dropped.

Checked:
    document   must be one of the evidence documents of the part (titles may be
               shortened, e.g. without "(pages 1-50 of 120)")
    page       "page N" / "p. N" must lie inside the part's pages of that PDF
    row        "row N" in an Excel text must be a row in the text sent
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from services.ai.attachments import Document
from services.assessment.data import CheckedStepFinding, Reference, StepFinding

PAGE_RANGE = re.compile(r"\((?:pages (\d+)-(\d+)|page (\d+)) of (\d+)\)\s*$")


def _base(title: str) -> str:
    """Title without a trailing "(...)" part label, lower-case, file name only."""
    title = re.sub(r"\s*\([^()]*\)\s*$", "", title.strip())
    return title.replace("\\", "/").rsplit("/", 1)[-1].lower()


class ReferenceChecker:
    def __init__(self, documents: List[Document]) -> None:
        self.documents = documents

    def check_finding(self, finding: StepFinding) -> CheckedStepFinding:
        problems: List[str] = []
        refs = [c.reference for c in finding.criteria] + [e.reference for e in finding.exceptions]
        for ref in refs:
            problem = self.problem(ref)
            if problem and problem not in problems:
                problems.append(problem)
        return CheckedStepFinding(**finding.model_dump(), reference_problems=problems)

    def problem(self, ref: Optional[Reference]) -> Optional[str]:
        if ref is None or not ref.document.strip():
            return None
        matches = self._documents(ref.document)
        if not matches:
            return f'"{ref.document}" is not one of the evidence documents sent'
        location = ref.location.lower()
        page = re.search(r"\b(?:page|p\.)\s*(\d+)", location)
        if page and all(d.mime_type == "application/pdf" for d in matches):
            number = int(page.group(1))
            if not any(self._has_page(d, number) for d in matches):
                return f'"{ref.document}" {ref.location}: page {number} was not in the evidence sent'
        row = re.search(r"\brow\s*(\d+)", location)
        if row and all(d.is_text and ".xls" in d.title.lower() for d in matches):
            number = int(row.group(1))
            if not any(re.search(rf"(?m)^\| {number}( |\b)", d.data.decode("utf-8", "replace")) for d in matches):
                return f'"{ref.document}" {ref.location}: row {number} was not in the evidence sent'
        return None

    def _documents(self, cited: str) -> List[Document]:
        exact = [d for d in self.documents if d.title == cited.strip()]
        return exact or [d for d in self.documents if _base(d.title) == _base(cited)]

    @staticmethod
    def _has_page(doc: Document, number: int) -> bool:
        match = PAGE_RANGE.search(doc.title)
        if match:
            first, last = (int(match.group(1)), int(match.group(2))) if match.group(1) else \
                (int(match.group(3)), int(match.group(3)))
            return first <= number <= last
        from services.evidences.evidence_splitter import _page_count

        return 1 <= number <= _page_count(doc.data)


def check_all(findings: Iterable[StepFinding], documents: List[Document]) -> List[CheckedStepFinding]:
    checker = ReferenceChecker(documents)
    return [checker.check_finding(f) for f in findings]
