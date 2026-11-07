"""ReferenceChecker: references must point at evidence that was actually sent."""
from __future__ import annotations

import unittest

from factories import PdfFactory
from services.ai.attachments import Document
from services.assessment.data import CriterionCheck, ExceptionItem, Reference, StepFinding
from services.assessment.references import ReferenceChecker

PDF_PART = Document(data=PdfFactory(pages=60).make(), title="ev/EV-05.pdf (pages 49-98 of 120)")
EXCEL = Document(data="| Row | A |\n|---|---|\n| 3 | x |\n| 14 | y |".encode(), title="EV-03.xlsx.md (Sheet 1 of 2)",
                 mime_type="text/plain")


class ReferenceCheckerTest(unittest.TestCase):
    def problem(self, document: str, location: str = ""):
        return ReferenceChecker([PDF_PART, EXCEL]).problem(Reference(document=document, location=location))

    def test_valid_references(self) -> None:
        self.assertIsNone(self.problem("EV-05.pdf", "page 60"))                       # short title is fine
        self.assertIsNone(self.problem("ev/EV-05.pdf (pages 49-98 of 120)", "p. 49"))
        self.assertIsNone(self.problem("EV-03.xlsx.md", 'Sheet 1 row 14, column A'))

    def test_wrong_document_page_or_row(self) -> None:
        self.assertIn("not one of the evidence documents", self.problem("EV-99.pdf"))
        self.assertIn("page 12 was not in the evidence sent", self.problem("EV-05.pdf", "page 12"))
        self.assertIn("row 15 was not in the evidence sent", self.problem("EV-03.xlsx.md", "row 15"))

    def test_problems_are_kept_with_the_finding(self) -> None:
        finding = StepFinding(
            step_reference="0472-04", relevance="contradicts",
            criteria=[CriterionCheck(criterion="c", kind="refusal", status="met",
                                     reference=Reference(document="EV-05.pdf", location="page 100"))],
            exceptions=[ExceptionItem(item="SD-1", description="d", reference=Reference(document="nope.pdf"))],
        )
        checked = ReferenceChecker([PDF_PART]).check_finding(finding)
        self.assertEqual(len(checked.reference_problems), 2)
        self.assertEqual(checked.relevance, "contradicts")


if __name__ == "__main__":
    unittest.main()
