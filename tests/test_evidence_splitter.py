"""EvidenceSplitter and evidence units, on factory-made files."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factories import ExcelFactory, MsgFactory, PdfFactory
from services.ai.attachments import Document
from services.evidences.docx_converter import DocxConverter
from services.evidences.evidence_service import EvidenceService
from services.evidences.evidence_splitter import EvidenceSplitter
from services.evidences.units import EvidenceUnit


def pdf_unit(pages: int) -> EvidenceUnit:
    doc = Document(data=PdfFactory(pages=pages).make(), title="EV-05.pdf")
    return EvidenceUnit(path=Path("EV-05.pdf"), kind="pdf", groups=[[doc]])


class PdfSplitTest(unittest.TestCase):
    def test_small_pdf_is_one_part(self) -> None:
        parts = EvidenceSplitter(max_pages=50).split(pdf_unit(10))
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].label, "EV-05.pdf")

    def test_page_ranges_overlap_and_keep_real_page_numbers(self) -> None:
        parts = EvidenceSplitter(max_pages=50, overlap_pages=2).split(pdf_unit(120))
        titles = [p.documents[0].title for p in parts]
        self.assertEqual(titles, ["EV-05.pdf (pages 1-50 of 120)", "EV-05.pdf (pages 49-98 of 120)",
                                  "EV-05.pdf (pages 97-120 of 120)"])
        self.assertEqual([p.label for p in parts][1], "EV-05.pdf (part 2 of 3)")

    def test_too_many_megabytes_halves_the_range(self) -> None:
        unit = pdf_unit(20)
        size_mb = len(unit.groups[0][0].data) / 1024 / 1024
        parts = EvidenceSplitter(max_pages=50, max_mb=size_mb / 3).split(unit)
        self.assertGreater(len(parts), 2)
        self.assertTrue(all(len(p.documents[0].data) <= size_mb / 3 * 1024 * 1024 for p in parts))


class EvidenceUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="kct-units-"))

    def service(self, **splitter) -> EvidenceService:
        return EvidenceService(self.root, docx=DocxConverter("python"),
                               splitter=EvidenceSplitter(**splitter)).case("case-001")

    def test_big_workbook_split_by_rows_with_header_in_every_block(self) -> None:
        case = self.service(max_tokens=5000)
        ExcelFactory(rows=300).create(case.root)
        parts = case.parts()
        self.assertGreater(len(parts), 2)
        for part in parts:
            text = part.documents[0].data.decode()
            self.assertIn("# Workbook: ", text)                    # workbook heading repeated
            self.assertIn("| Row | A |", text)                      # table header repeated
            self.assertLessEqual(part.estimated_tokens, 5000)
        picture = [p for p in parts if any(d.is_image for d in p.documents)]
        self.assertEqual(len(picture), 1)
        self.assertIn("Summary", "".join(d.title for d in picture[0].documents))   # picture with its sheet

    def test_email_text_goes_with_every_part(self) -> None:
        case = self.service(max_tokens=3000)
        MsgFactory(history=2, images=2).create(case.root)
        parts = case.parts()
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertTrue(part.documents[0].title.endswith(".msg.md"))
        self.assertEqual(len({p.unit for p in parts}), 1)                      # one unit

    def test_converted_files_are_not_units(self) -> None:
        case = self.service()
        MsgFactory().create(case.root)
        case.units()                                                          # converts
        self.assertEqual([str(p) for p in case.evidence_files()], [MsgFactory.name])


if __name__ == "__main__":
    unittest.main()
