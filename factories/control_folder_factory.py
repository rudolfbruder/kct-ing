"""ControlFolderFactory: a fake control folder in the SharePoint structure.

    ControlFolderFactory().create(root)      writes root/<name>/Input/..., returns the control folder
    ControlFolderFactory().zip()             the same as a ZIP (as SharePoint's Download gives it)
    ControlFolderFactory().zip(flat=True)    all files in one folder, no structure

    <name>/                                   "5.0 Password resets of privileged accounts (SAMPLE)"
    └── Input/
        ├── Evidence/
        │   ├── EV-01_..._SAMPLE.docx           Word (DocxFactory)
        │   ├── EV-04_..._SAMPLE.msg            email thread with attachments (MsgFactory)
        │   ├── EV-05_..._SAMPLE.pdf            PDF log (PdfFactory)
        │   ├── Q1 2026/EV-03_..._SAMPLE.xlsx   Excel in a subfolder (ExcelFactory)
        │   └── meeting notes.pptx              a type that is not accepted (shows skipping)
        └── Test Plan and Control Details/
            ├── Control Details CTL-IAM-0472 (SAMPLE).docx
            └── Test Plan TP-PRC-IAM-014 2026Q1 (SAMPLE).pdf

Office lock files (~$...) and .DS_Store are added too: the import must ignore them.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Union

from factories.docx_factory import DocxFactory
from factories.excel_factory import ExcelFactory
from factories.msg_factory import MsgFactory
from factories.pdf_factory import PdfFactory

CONTROL_DETAILS = "Control Details CTL-IAM-0472 (SAMPLE).docx"
TEST_PLAN = "Test Plan TP-PRC-IAM-014 2026Q1 (SAMPLE).pdf"


class ControlFolderFactory:
    name = "5.0 Password resets of privileged accounts (SAMPLE)"

    def __init__(self, name: str = "", excel_rows: int = 40, pdf_pages: int = 12) -> None:
        self.name = name or self.name
        self.excel_rows = excel_rows
        self.pdf_pages = pdf_pages

    def create(self, root: Union[str, Path]) -> Path:
        control = Path(root) / self.name
        evidence = control / "Input" / "Evidence"
        documents = control / "Input" / "Test Plan and Control Details"
        for folder in (evidence / "Q1 2026", documents):
            folder.mkdir(parents=True, exist_ok=True)

        (documents / CONTROL_DETAILS).write_bytes(self.control_details())
        (documents / TEST_PLAN).write_bytes(self.test_plan())
        (documents / f"~${CONTROL_DETAILS[:20]}.docx").write_bytes(b"lock")

        DocxFactory().create(evidence)
        MsgFactory(history=2, images=2).create(evidence)
        PdfFactory(pages=self.pdf_pages).create(evidence)
        ExcelFactory(rows=self.excel_rows).create(evidence / "Q1 2026")
        (evidence / "meeting notes.pptx").write_bytes(b"PK\x03\x04 not accepted as evidence")
        (evidence / ".DS_Store").write_bytes(b"\x00")
        return control

    def zip(self, flat: bool = False) -> bytes:
        """The control folder as a ZIP, like SharePoint's Download. flat=True: all files in one
        folder without the structure, so every file has to be sorted by content."""
        import tempfile
        import zipfile

        with tempfile.TemporaryDirectory() as work:
            control = self.create(work)
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(control.rglob("*")):
                    if not path.is_file():
                        continue
                    name = path.name if flat else str(path.relative_to(Path(work)))
                    archive.write(path, name)
            return buffer.getvalue()

    @staticmethod
    def control_details() -> bytes:
        from docx import Document

        doc = Document()
        doc.add_heading("Control Details: CTL-IAM-0472 (SAMPLE)", level=0)
        rows = [("Control ID", "CTL-IAM-0472"), ("Process", "PRC-IAM-014 Privileged access management"),
                ("Owner", "Head of IAM Operations"), ("Frequency", "Event-driven (each password reset)"),
                ("Risk", "Unauthorised access to privileged accounts through social engineering of the service desk")]
        table = doc.add_table(rows=0, cols=2)
        table.style = "Table Grid"
        for label, value in rows:
            cells = table.add_row().cells
            cells[0].text, cells[1].text = label, value
        doc.add_heading("Control activity", level=1)
        for step in ("The service desk agent verifies the caller's identity with at least two approved factors "
                     "before resetting a privileged account's password.",
                     "Verification and reset are performed by the same agent and recorded on the ticket.",
                     "Emergency resets require written approval by the Head of IAM Operations."):
            doc.add_paragraph(step, style="List Number")
        doc.add_heading("Evidence produced", level=1)
        doc.add_paragraph("EV-01 ServiceNow tickets, EV-03 ADX audit log extract, EV-04 approval emails.")
        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def test_plan() -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        y = A4[1] - 60
        lines = [
            ("Helvetica-Bold", 14, "Test Plan TP-PRC-IAM-014, 2026 Q1 (SAMPLE)"),
            ("Helvetica", 10, "Control under test: CTL-IAM-0472. Testing period: 1 January - 31 March 2026."),
            ("Helvetica", 10, "Population: password resets of privileged accounts (ADX audit log). Sample: 25."),
            ("Helvetica-Bold", 11, "Test steps"),
            ("Helvetica", 10, "0472-01 Identity verification recorded on the ticket (EV-01)."),
            ("Helvetica", 10, "0472-02 At least two approved factors applied."),
            ("Helvetica", 10, "0472-04 Verification precedes the reset; same agent verifies and resets (EV-01, EV-03)."),
            ("Helvetica", 10, "0472-05 Emergency resets approved in writing (EV-04)."),
            ("Helvetica-Bold", 11, "Exceptions"),
            ("Helvetica", 10, "Any reset before verification, or by another agent than the verifier, is an exception."),
        ]
        for font, size, text in lines:
            pdf.setFont(font, size)
            pdf.drawString(50, y, text)
            y -= 22
        pdf.save()
        return buffer.getvalue()
