"""DocxAttachmentsFactory: a fake Word evidence document with files embedded in it.

    DocxAttachmentsFactory().create(folder)     writes EV-07_..._SAMPLE.docx, returns the path
    DocxAttachmentsFactory().make()              the .docx as bytes

Made-up data. The document embeds, the two ways Word does it (see
services/evidences/docx_attachments.py):

    1  an Excel workbook        as a package (Insert > Object > Excel)
    2  a PDF                    as an OLE object, Ole10Native (a file dropped into Word)
    3  an Outlook email (.msg)  as an OLE object, Ole10Native
    4  a Word document          as a package; it has its own embedded file (a .txt),
                                so nesting can be tried

Needs python-docx, openpyxl, Pillow and extract-msg (its OleWriter writes the OLE files).
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Union

from factories.excel_factory import ExcelFactory
from factories.msg_factory import MsgFactory
from factories.pdf_factory import PdfFactory
from services.evidences.docx_attachments import make_ole10native

WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
OLE = "application/vnd.openxmlformats-officedocument.oleObject"
REL_PACKAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package"
REL_OLE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"


def ole_package(name: str, data: bytes) -> bytes:
    """An OLE object the way Word stores a dropped-in file: an Ole10Native stream."""
    from extract_msg.ole_writer import OleWriter

    writer = OleWriter()
    writer.addEntry(["\x01Ole10Native"], data=make_ole10native(name, data))
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def word_with(title: str, lines: List[str], embedded: List[Tuple[str, str, str, bytes, str]]) -> bytes:
    """A .docx with these lines and embedded objects (label, part name, content type, bytes, kind)."""
    from docx import Document
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import parse_xml

    document = Document()
    document.add_heading(title, level=1)
    for line in lines:
        document.add_paragraph(line)
    for label, part_name, content_type, blob, kind in embedded:
        document.add_paragraph(f"Attached: {label}")
        part = Part(PackURI(f"/word/embeddings/{part_name}"), content_type, blob, document.part.package)
        rel_id = document.part.relate_to(part, REL_OLE if kind == "ole" else REL_PACKAGE)
        prog = "Package" if kind == "ole" else ("Excel.Sheet.12" if content_type == EXCEL else "Word.Document.12")
        run = document.add_paragraph().add_run()
        run._r.append(parse_xml(
            '<w:object xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:o="urn:schemas-microsoft-com:office:office" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<o:OLEObject Type="Embed" ProgID="{prog}" ShapeID="_x0000_i10{len(rel_id)}" '
            f'DrawAspect="Icon" ObjectID="_{abs(hash(part_name)) % 10**10}" r:id="{rel_id}"/></w:object>'))
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class DocxAttachmentsFactory:
    name = "EV-07_access_review_with_attachments_SAMPLE.docx"

    def make(self) -> bytes:
        inner = word_with(
            "Reviewer notes (SAMPLE)",
            ["Notes of the reviewer, embedded in the main access review document."],
            [("checklist.txt", "oleObject1.bin", OLE,
              ole_package("checklist.txt", b"1. List of users exported\n2. Reviewed by manager\n"), "ole")])
        return word_with(
            "EV-07 Quarterly access review, Q1 2026 (SAMPLE)",
            ["Made-up sample data. The evidence for this review is attached below:",
             "the user list (Excel), the signed review (PDF), the approval email and the reviewer notes."],
            [("User list (Excel)", "Microsoft_Excel_Worksheet.xlsx", EXCEL, ExcelFactory().make(), "package"),
             ("Signed review (PDF)", "oleObject1.bin", OLE, ole_package("Signed review Q1.pdf", PdfFactory().make()), "ole"),
             ("Approval email", "oleObject2.bin", OLE, ole_package("Approval access review.msg", MsgFactory().make()), "ole"),
             ("Reviewer notes (Word)", "Microsoft_Word_Document.docx", WORD, inner, "package")])

    def create(self, target: Union[str, Path]) -> Path:
        path = Path(target)
        if path.suffix.lower() != ".docx":
            path = path / self.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.make())
        return path
