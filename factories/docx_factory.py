"""DocxFactory: a fake Word evidence document (Laravel: a model factory).

    DocxFactory().create(folder)          writes EV-01_..._SAMPLE.docx into folder, returns the path
    DocxFactory().create(path / "x.docx") writes exactly there
    DocxFactory().make()                  the .docx as bytes (for example as an email attachment)

Made-up data for the sample case PRC-IAM-014: headings, bold and italic text,
a bullet list, a table and a screenshot. Needs python-docx and Pillow.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Union

from factories.images import RESETS, audit_log_screenshot


class DocxFactory:
    name = "EV-01_password_reset_tickets_SAMPLE.docx"

    def make(self) -> bytes:
        from docx import Document
        from docx.shared import Cm

        doc = Document()
        doc.add_heading("EV-01 Service desk tickets: password resets (SAMPLE)", level=0)

        paragraph = doc.add_paragraph()
        paragraph.add_run("Control: ").bold = True
        paragraph.add_run("CTL-IAM-0472, identity verification before password reset.")
        paragraph = doc.add_paragraph()
        paragraph.add_run("Period: ").bold = True
        paragraph.add_run("2026 Q1. ")
        paragraph.add_run("Made-up sample data for testing the pipeline.").italic = True

        doc.add_heading("1. Scope", level=1)
        doc.add_paragraph(
            "Extract of ServiceNow service desk tickets for password resets of privileged accounts. "
            "Each ticket must record the identity verification before the reset is executed, "
            "and the same agent must verify and execute."
        )
        for item in ("Source system: ServiceNow SD", "Sample size: 3 of 25 (excerpt)", "Prepared by: IAM Operations"):
            doc.add_paragraph(item, style="List Bullet")

        doc.add_heading("2. Sampled tickets", level=1)
        table = doc.add_table(rows=1, cols=6)
        table.style = "Table Grid"
        headers = ["Ticket", "Verified at", "Reset at", "Verified by", "Executed by", "Verification factors"]
        for cell, text in zip(table.rows[0].cells, headers):
            cell.paragraphs[0].add_run(text).bold = True
        for row in RESETS:
            cells = table.add_row().cells
            for cell, text in zip(cells, row):
                cell.text = text

        doc.add_heading("3. Audit log screenshot", level=1)
        doc.add_paragraph("Reset execution events from the ADX audit log for the same tickets:")
        doc.add_picture(audit_log_screenshot(), width=Cm(16))

        doc.add_heading("4. Notes", level=1)
        doc.add_paragraph(
            "SD-105112: the reset timestamp is one minute before the verification timestamp, and the "
            "reset was executed by a different agent than the one who verified."
        )


        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    def create(self, target: Union[str, Path]) -> Path:
        """Write the document. target is a folder (the default name is used) or a file path."""
        path = Path(target)
        if path.suffix.lower() != ".docx":
            path = path / self.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.make())
        return path
