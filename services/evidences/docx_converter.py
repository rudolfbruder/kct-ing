"""DocxConverter: Word documents (.docx) to PDF, because Gemini and Claude read PDFs, not .docx.

    converter = DocxConverter()                 # engine "auto"
    result = converter.convert(Path("EV-01.docx"))
    result.pdf                                   # EV-01.pdf next to it
    result.engine                                # "libreoffice" or "python"

Two engines:

    libreoffice   soffice --headless --convert-to pdf. Keeps the Word layout
                  exactly. Used when LibreOffice is installed.
    python        python-docx reads the document, reportlab writes the PDF.
                  Needs only pip packages, so it works on a workbench without
                  LibreOffice. Keeps the content (headings, paragraphs, bold and
                  italic, lists, tables, images) but not the exact Word layout:
                  columns, text boxes, headers and footers are dropped.

"auto" picks libreoffice when it is installed, python otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

from services.evidences import libreoffice
from services.evidences.exceptions import ConversionError

ENGINES = ("auto", "libreoffice", "python")

# Fonts tried in this order for the python engine (regular, bold, italic, bold italic).
# DejaVu is on most Linux workbenches, Arial on macOS; reportlab's bundled Vera
# (Western European letters only) is the last resort.
FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/dejavu/DejaVuSans-Oblique.ttf", "/usr/share/fonts/dejavu/DejaVuSans-BoldOblique.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Arial Italic.ttf", "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"),
]
FONT_NAME = "KctSans"


@dataclass(frozen=True)
class DocxConversion:
    source: Path
    pdf: Path
    engine: str

    @property
    def output(self) -> Path:
        return self.pdf

    @property
    def files(self) -> list:
        """Everything to send to the model."""
        return [self.pdf]


class DocxConverter:
    def __init__(self, engine: str = "auto") -> None:
        self._check_engine(engine)
        self.engine = engine

    def convert(self, source: Path, pdf: Optional[Path] = None, engine: Optional[str] = None) -> DocxConversion:
        """Convert one .docx file. The PDF goes next to it unless pdf is given."""
        source = Path(source)
        engine = engine or self.engine
        self._check_engine(engine)
        if source.suffix.lower() != ".docx":
            raise ConversionError(f"{source.name}: only .docx is supported")
        if not source.is_file():
            raise ConversionError(f"{source} does not exist")
        pdf = Path(pdf) if pdf else source.with_suffix(".pdf")
        pdf.parent.mkdir(parents=True, exist_ok=True)

        if engine == "auto":
            engine = "libreoffice" if libreoffice.binary() else "python"
        if engine == "libreoffice":
            libreoffice.to_pdf(source, pdf, timeout=180)
        else:
            self._with_python(source, pdf)
        return DocxConversion(source=source, pdf=pdf, engine=engine)

    @staticmethod
    def _check_engine(engine: str) -> None:
        if engine not in ENGINES:
            raise ConversionError(f"engine must be one of {ENGINES}, got {engine!r}")

    # --- python engine ---------------------------------------------------------

    def _with_python(self, source: Path, pdf: Path) -> None:
        try:
            import docx
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph as PdfParagraph, SimpleDocTemplate, Spacer
        except ImportError as exc:
            raise ConversionError(f"Missing package for the python engine: {exc.name}. "
                                  "pip install python-docx reportlab") from exc

        document = docx.Document(str(source))
        width = A4[0] - 4 * cm
        styles = self._styles(self._register_font())

        story = []
        # Body order: paragraphs and tables as they appear in the document.
        for child in document.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                story.extend(self._paragraph(Paragraph(child, document), document, styles, width))
            elif tag == "tbl":
                table = self._table(Table(child, document), styles, width)
                if table is not None:
                    story += [table, Spacer(1, 8)]
        if not story:
            story.append(PdfParagraph("(empty document)", styles["body"]))

        SimpleDocTemplate(
            str(pdf), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
            bottomMargin=2 * cm, title=source.stem,
        ).build(story)

    @staticmethod
    def _styles(font: str) -> dict:
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

        base = getSampleStyleSheet()
        styles = {
            "body": ParagraphStyle("body", parent=base["BodyText"], fontName=font, fontSize=10, leading=13),
            "title": ParagraphStyle("title", parent=base["Title"], fontName=f"{font}-Bold"),
            "cell": ParagraphStyle("cell", parent=base["BodyText"], fontName=font, fontSize=9, leading=11),
        }
        for level, size in ((1, 16), (2, 13), (3, 11)):
            styles[f"h{level}"] = ParagraphStyle(
                f"h{level}", parent=base[f"Heading{level}"], fontName=f"{font}-Bold", fontSize=size
            )
        return styles

    @staticmethod
    def _markup(paragraph) -> str:
        """The paragraph's text as reportlab markup, keeping bold, italic and underline."""
        parts = []
        for run in paragraph.runs:
            text = escape(run.text).replace("\n", "<br/>")
            if not text:
                continue
            if run.bold:
                text = f"<b>{text}</b>"
            if run.italic:
                text = f"<i>{text}</i>"
            if run.underline:
                text = f"<u>{text}</u>"
            parts.append(text)
        return "".join(parts)

    def _paragraph(self, paragraph, document, styles: dict, width: float) -> list:
        from reportlab.platypus import Paragraph as PdfParagraph

        style_name = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        markup = self._markup(paragraph)
        flowables = []
        if markup.strip():
            if style_name == "title":
                style = styles["title"]
            elif style_name.startswith("heading"):
                style = styles.get(f"h{style_name.replace('heading', '').strip()}", styles["h3"])
            else:
                style = styles["body"]
            if "list" in style_name:
                markup = "• " + markup
            flowables.append(PdfParagraph(markup, style))
        flowables.extend(self._images(paragraph, document, width))
        return flowables

    @staticmethod
    def _images(paragraph, document, width: float) -> list:
        """Pictures in the paragraph, scaled down to the page width."""
        from reportlab.platypus import Image

        found = []
        for blip in paragraph._element.xpath(".//a:blip"):
            rel_id = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            part = document.part.related_parts.get(rel_id)
            if part is None:
                continue
            image = Image(BytesIO(part.blob))
            scale = min(1.0, width / image.drawWidth)
            image.drawWidth *= scale
            image.drawHeight *= scale
            found.append(image)
        return found

    def _table(self, table, styles: dict, width: float):
        from reportlab.lib import colors
        from reportlab.platypus import Paragraph as PdfParagraph, Table as PdfTable, TableStyle

        rows = [
            [PdfParagraph("<br/>".join(m for m in (self._markup(p) for p in cell.paragraphs) if m), styles["cell"])
             for cell in row.cells]
            for row in table.rows
        ]
        if not rows:
            return None
        columns = max(len(r) for r in rows)
        rows = [r + [""] * (columns - len(r)) for r in rows]
        pdf_table = PdfTable(rows, colWidths=[width / columns] * columns, repeatRows=1)
        pdf_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return pdf_table

    @staticmethod
    def _register_font() -> str:
        """Register a TrueType font family once and return its name."""
        import reportlab
        from reportlab.lib.fonts import addMapping
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        if FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return FONT_NAME
        vera = Path(reportlab.__file__).parent / "fonts"
        candidates = FONT_CANDIDATES + [
            (str(vera / "Vera.ttf"), str(vera / "VeraBd.ttf"), str(vera / "VeraIt.ttf"), str(vera / "VeraBI.ttf"))
        ]
        for regular, bold, italic, bold_italic in candidates:
            faces = {"": regular, "-Bold": bold, "-Italic": italic, "-BoldItalic": bold_italic}
            if all(Path(path).is_file() for path in faces.values()):
                for suffix, path in faces.items():
                    pdfmetrics.registerFont(TTFont(FONT_NAME + suffix, path))
                addMapping(FONT_NAME, 0, 0, FONT_NAME)
                addMapping(FONT_NAME, 1, 0, FONT_NAME + "-Bold")
                addMapping(FONT_NAME, 0, 1, FONT_NAME + "-Italic")
                addMapping(FONT_NAME, 1, 1, FONT_NAME + "-BoldItalic")
                return FONT_NAME
        return "Helvetica"
