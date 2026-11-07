"""PdfFactory: a fake multi-page PDF evidence document, for trying out splitting.

    PdfFactory(pages=120).create(folder)     writes EV-05_..._SAMPLE.pdf, returns the path
    PdfFactory(pages=3).make()               the PDF as bytes

Every page has a heading "Page N of M", a few lines of made-up ticket log, and
(every 10th page) a screenshot, so pages are not all the same. Needs reportlab.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Union

from factories.images import ticket_screenshot


class PdfFactory:
    name = "EV-05_service_desk_log_export_SAMPLE.pdf"

    def __init__(self, pages: int = 120) -> None:
        self.pages = max(1, pages)

    def make(self) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        pdf.setTitle("Service desk log export (SAMPLE)")
        for page in range(1, self.pages + 1):
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(50, height - 60, f"Service desk log export, 2026 Q1 (SAMPLE) - Page {page} of {self.pages}")
            pdf.setFont("Helvetica", 9)
            y = height - 90
            for line in range(25):
                ticket = 104200 + (page * 25 + line) * 7
                pdf.drawString(50, y, f"SD-{ticket}  2026-0{1 + page % 3}-{1 + line:02d} 08:{line:02d}  "
                                      f"RESET_PASSWORD  verified_by=AGT-0{193 + line % 4}  status=Closed")
                y -= 14
            if page % 10 == 0:
                pdf.drawImage(ImageReader(ticket_screenshot(f"SD-{104200 + page}")), 50, 120, width=480, height=146)
            pdf.showPage()
        pdf.save()
        return buffer.getvalue()

    def create(self, target: Union[str, Path]) -> Path:
        path = Path(target)
        if path.suffix.lower() != ".pdf":
            path = path / self.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.make())
        return path
