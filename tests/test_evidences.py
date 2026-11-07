"""Evidence service and the .docx to PDF conversion (python engine)."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from factories import DocxFactory, ExcelFactory, MsgFactory
from services.evidences.evidence_service import EvidenceService
from services.evidences.docx_converter import DocxConverter
from services.evidences.exceptions import ConversionError


class EvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="kct-evidence-"))
        self.service = EvidenceService(self.root)
        self.python_service = EvidenceService(self.root, docx=DocxConverter("python"))
        DocxFactory().create(self.root / "sub")

    def test_converts_docx_with_table_and_picture_to_pdf(self) -> None:
        result = self.service.convert_to_pdf(Path("sub") / DocxFactory.name, engine="python")
        self.assertEqual(result.engine, "python")
        self.assertEqual(result.pdf, self.root / "sub" / DocxFactory.name.replace(".docx", ".pdf"))
        data = result.pdf.read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertIn(b"/Subtype /Image", data)  # the screenshot made it

    def test_files_are_found_recursively_and_relative(self) -> None:
        self.assertEqual(self.service.files(), [Path("sub") / DocxFactory.name])

    def test_convert_all_skips_up_to_date_pdfs(self) -> None:
        self.assertEqual(len(self.python_service.convert_all_word()), 1)
        self.assertEqual(self.python_service.convert_all_word(), [])
        docx = self.root / "sub" / DocxFactory.name
        later = time.time() + 5
        os.utime(docx, (later, later))
        self.assertEqual(len(self.python_service.convert_all_word()), 1)

    def test_rejects_other_files(self) -> None:
        other = self.root / "notes.txt"
        other.write_text("x")
        with self.assertRaises(ConversionError):
            DocxConverter("python").convert(other)
        with self.assertRaises(ConversionError):
            DocxConverter("python").convert(self.root / "missing.docx")



class ExcelEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="kct-excel-"))
        cls.service = EvidenceService(cls.root)
        ExcelFactory().create(cls.root)
        cls.result = cls.service.convert_excel(ExcelFactory.name, with_pdf=False)
        cls.text = cls.result.text.read_text(encoding="utf-8")

    def test_every_sheet_with_excel_coordinates(self) -> None:
        self.assertEqual([s.name for s in self.result.sheets], ["Reset events", "User master", "Summary", "Lookup"])
        self.assertEqual((self.result.sheets[0].rows, self.result.sheets[0].columns), (103, 20))
        self.assertIn("| Row | A | B | C |", self.text)
        self.assertIn('## Sheet 4 of 4: "Lookup" (HIDDEN sheet)', self.text)

    def test_formatting_that_csv_would_lose(self) -> None:
        self.assertIn("{row fill: light red}", self.text)              # exception rows
        self.assertIn("{text: red}", self.text)                         # red executor
        self.assertIn('{comment: "Only one factor? Check with service desk." (Reviewer)}', self.text)
        self.assertIn("{merged A1:T1}", self.text)
        self.assertIn("S (hidden)", self.text)                         # hidden column
        self.assertIn("| 10 (hidden)", self.text)                       # hidden row in User master
        self.assertIn("{formula, not calculated}", self.text)
        self.assertIn("Conditional formatting on B4", self.text)

    def test_pictures_are_extracted_and_placed(self) -> None:
        self.assertEqual(len(self.result.images), 1)
        self.assertTrue(self.result.images[0].read_bytes().startswith(b"\x89PNG"))
        self.assertIn("| 2 | Control | CTL-IAM-0472 |  | {image 1: attached as sheet3_image1.png} |", self.text)

    def test_attachments_are_what_the_models_accept(self) -> None:
        documents = {d.title: d.mime_type for d in self.service.attachments()}
        self.assertEqual(documents[EXCEL_NAME_MD], "text/plain")
        self.assertEqual(documents[f"{EXCEL_NAME_IMAGES}/sheet3_image1.png"], "image/png")
        self.assertNotIn(EXCEL_NAME, str(documents.keys()).replace(EXCEL_NAME_MD, "").replace(EXCEL_NAME_IMAGES, ""))

    def test_convert_all_excel_skips_up_to_date(self) -> None:
        self.assertEqual(self.service.convert_all_excel(), [])



class MsgEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="kct-msg-"))
        cls.service = EvidenceService(cls.root, docx=DocxConverter("python"))
        MsgFactory().create(cls.root)
        cls.result = cls.service.convert(MsgFactory.name)
        cls.text = cls.result.text.read_text(encoding="utf-8")

    def test_factory_writes_a_real_outlook_file(self) -> None:
        import extract_msg

        message = extract_msg.openMsg(str(self.root / MsgFactory.name))
        try:
            self.assertEqual(message.subject, "RE: Evidence request CTL-IAM-0472 (SAMPLE)")
            self.assertEqual(len(message.attachments), 4)
        finally:
            message.close()

    def test_header_and_body_from_html(self) -> None:
        self.assertIn("| From | Anna Bak <anna.bak@example.com> |", self.text)
        self.assertIn("| Cc | IAM Operations <iam.ops@example.com> |", self.text)
        self.assertIn("- EV-03: ADX audit log extract (Excel)", self.text)           # HTML list
        self.assertIn("one minute before verification {text: red}", self.text)      # colored text
        self.assertIn("[inline image: image001.png]", self.text)                    # where the picture sits
        self.assertIn("Subject: Evidence request CTL-IAM-0472", self.text)          # quoted earlier email
        self.assertIn("| Earlier emails quoted in the thread | 2 |", self.text)
        self.assertIn("### Earlier email 2 of 2 (quoted in the thread)", self.text)
        self.assertIn("the evidence folder (https://example.sharepoint.com/", self.text)  # link kept

    def test_attachments_go_through_the_other_converters(self) -> None:
        kinds = {a.kind: a for a in self.result.attachments}
        self.assertEqual(set(kinds), {"word", "excel", "image", "email"})
        self.assertEqual(kinds["word"].outputs[0].suffix, ".pdf")
        self.assertTrue(kinds["excel"].outputs[0].name.endswith(".xlsx.md"))
        self.assertEqual(kinds["image"].note, "shown inside the body")
        nested = kinds["email"].outputs[0].read_text(encoding="utf-8")
        self.assertIn("# Email: Approval: emergency password reset SD-105112", nested)
        self.assertIn("| From | Mark Pol <mark.pol@example.com> |", nested)

    def test_everything_is_readable_by_the_models(self) -> None:
        from services.ai.attachments import MIME_TYPES

        self.assertTrue(all(f.suffix.lower() in MIME_TYPES for f in self.result.files))
        titles = [d.title for d in self.service.attachments()]
        self.assertIn(MsgFactory.name + ".md", titles)
        self.assertFalse(any(t.endswith((".docx", ".xlsx", ".msg")) for t in titles))

    def test_convert_all_skips_converted_email_and_its_attachments(self) -> None:
        self.assertEqual(self.service.convert_all(), [])

    def test_unreadable_attachment_is_listed_not_fatal(self) -> None:
        from factories.msg_factory import Attachment, Email, TO
        from datetime import datetime, timezone

        email = Email("Odd attachment", ("A", "a@example.com"), [("B", "b@example.com", TO)],
                      datetime(2026, 1, 1, tzinfo=timezone.utc), "See zip.",
                      attachments=[Attachment("logs.zip", "application/zip", b"PK\x03\x04")])
        path = MsgFactory().create(self.root / "odd.msg", email)
        result = self.service.convert(path.name)
        self.assertIn("not sent to the AI: .zip is not a readable format", result.text.read_text(encoding="utf-8"))



class MsgThreadTest(unittest.TestCase):
    """MsgFactory options and how the converter splits a long thread."""

    def convert(self, factory: MsgFactory) -> str:
        root = Path(tempfile.mkdtemp(prefix="kct-thread-"))
        path = factory.create(root)
        return EvidenceService(root, docx=DocxConverter("python")).convert(path.name).text.read_text(encoding="utf-8")

    def test_long_thread_is_split_into_numbered_earlier_emails(self) -> None:
        text = self.convert(MsgFactory(history=10, images=4, attachments=False))
        self.assertIn("| Earlier emails quoted in the thread | 10 |", text)
        self.assertIn("### Earlier email 10 of 10 (quoted in the thread)", text)
        # oldest last: the original request, then the reminders added beyond the 8 written messages
        self.assertLess(text.index("Reminder 2"), text.index("Please send the evidence for the password resets"))
        for number in range(1, 5):
            self.assertIn(f"[inline image: image{number:03d}.png]", text)

    def test_single_email_without_links_images_or_attachments(self) -> None:
        text = self.convert(MsgFactory(history=0, images=0, links=False, attachments=False))
        self.assertNotIn("Earlier email", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("[inline image", text)
        self.assertNotIn("## Attachments", text)

    def test_plain_text_version_keeps_links_like_outlook(self) -> None:
        body = MsgFactory(history=3).email().body
        self.assertIn("SD-105112 <https://servicenow.example.com/", body)
        self.assertEqual(body.count("________________________________"), 3)


EXCEL_NAME = ExcelFactory.name
EXCEL_NAME_MD = EXCEL_NAME + ".md"
EXCEL_NAME_IMAGES = EXCEL_NAME + "_images"


if __name__ == "__main__":
    unittest.main()
