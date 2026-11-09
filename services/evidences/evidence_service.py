"""EvidenceService: the evidence files the assessment will judge test steps against.

Finds the files and decides which converter handles which file; the
conversion itself is in DocxConverter (Word to PDF), ExcelConverter (Excel to
text + pictures) and MsgConverter (Outlook email to text, attachments
converted with the other two). Files live under KCT_EVIDENCES_ROOT (default
storage/evidences). The production folder layout is not known yet, so nothing
here assumes one: files are found recursively and paths are relative to the root.

    kct.evidences.files()                      every evidence file
    kct.evidences.convert("x.docx")            Word or Excel, picks the converter by extension
    kct.evidences.convert_all()                every file whose output is missing or outdated
    kct.evidences.attachments()                everything the AI can read, as Documents

    kct.evidences.convert_to_pdf("x.docx")     only Word: x.pdf next to it
    kct.evidences.convert_excel("y.xlsx")      only Excel: y.xlsx.md (+ pictures, + PDF with LibreOffice)
    kct.evidences.convert_email("z.msg")       only email: z.msg.md + z.msg_attachments/ (converted)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Union

from services.ai.attachments import MIME_TYPES, Document
from services.evidences.docx_converter import DocxConversion, DocxConverter
from services.evidences.excel_converter import EXCEL_SUFFIXES, ExcelConversion, ExcelConverter
from services.evidences.exceptions import ConversionError
from services.evidences.msg_converter import MsgConversion, MsgConverter

log = logging.getLogger("kct")

PathLike = Union[str, Path]



class EvidenceService:
    def __init__(
        self,
        root: Path,
        docx: Optional[DocxConverter] = None,
        excel: Optional[ExcelConverter] = None,
        msg: Optional[MsgConverter] = None,
    ) -> None:
        self.root = Path(root)
        self.docx = docx or DocxConverter()
        self.excel = excel or ExcelConverter()
        self.msg = msg or MsgConverter(self.docx, self.excel)

    # --- files -------------------------------------------------------------------

    def files(self, pattern: str = "*") -> List[Path]:
        """Evidence files under the root (recursively), relative to it, sorted."""
        if not self.root.is_dir():
            return []
        return sorted(p.relative_to(self.root) for p in self.root.rglob(pattern) if p.is_file())

    def path(self, name: PathLike) -> Path:
        """Absolute path of an evidence file given relative to the root (or already absolute)."""
        path = Path(name)
        return path if path.is_absolute() else self.root / path

    def attachments(self) -> List[Document]:
        """Every file under the root the AI can read: PDFs, converted workbooks (.md) and pictures.

        Titles are paths relative to the root, so the model can tell files in
        different subfolders apart.
        """
        return [
            Document.from_path(self.root / relative, title=str(relative))
            for relative in self.files()
            if relative.suffix.lower() in MIME_TYPES
        ]


    # --- conversion ----------------------------------------------------------------

    def convert(self, name: PathLike, force_engine: Optional[str] = None) -> Union[DocxConversion, ExcelConversion, MsgConversion]:
        """Convert one Word, Excel or email file with the matching converter."""
        suffix = Path(name).suffix.lower()
        if suffix == ".docx":
            return self.convert_to_pdf(name, engine=force_engine)
        if suffix in EXCEL_SUFFIXES:
            return self.convert_excel(name)
        if suffix == ".msg":
            return self.convert_email(name)
        raise ConversionError(f"{Path(name).name}: no converter for {suffix or 'files without extension'}")

    def convert_to_pdf(self, name: PathLike, pdf: Optional[PathLike] = None, engine: Optional[str] = None) -> DocxConversion:
        source = self.path(name)
        result = self.docx.convert(source, Path(pdf) if pdf else None, engine)
        log.info("evidence %s converted to %s (%s)", source, result.pdf, result.engine)
        return result

    def convert_excel(self, name: PathLike, with_pdf: Optional[bool] = None) -> ExcelConversion:
        source = self.path(name)
        result = self.excel.convert(source, with_pdf)
        log.info("evidence %s converted to %s (%d picture(s), %s)",
                 source, result.text, len(result.images), result.engine)
        return result

    def convert_email(self, name: PathLike) -> MsgConversion:
        source = self.path(name)
        result = self.msg.convert(source)
        log.info("evidence %s converted to %s (%d attachment(s))", source, result.text, len(result.attachments))
        return result

    def convert_all(self, force: bool = False, word: bool = True, excel: bool = True, email: bool = True) -> list:
        """Convert every Word, Excel and email file whose output is missing or older than the file.

        Attachments inside email folders (*.msg_attachments) are converted by the email's
        conversion, so they are skipped here.
        """
        done = []
        for relative in self.files():
            if relative.name.startswith("~$"):  # Office lock files
                continue
            if any(part.endswith(".msg_attachments") for part in relative.parts[:-1]):
                continue
            suffix = relative.suffix.lower()
            source = self.root / relative
            if word and suffix == ".docx":
                if force or self._outdated(source, source.with_suffix(".pdf")):
                    done.append(self.convert_to_pdf(source))
            elif excel and suffix in EXCEL_SUFFIXES:
                if force or self._outdated(source, source.with_name(source.name + ".md")):
                    done.append(self.convert_excel(source))
            elif email and suffix == ".msg":
                if force or self._outdated(source, source.with_name(source.name + ".md")):
                    done.append(self.convert_email(source))
        return done

    def convert_all_word(self, force: bool = False) -> List[DocxConversion]:
        return self.convert_all(force=force, excel=False, email=False)

    def convert_all_excel(self, force: bool = False) -> List[ExcelConversion]:
        return self.convert_all(force=force, word=False, email=False)

    def convert_all_email(self, force: bool = False) -> List[MsgConversion]:
        return self.convert_all(force=force, word=False, excel=False)

    @staticmethod
    def _outdated(source: Path, output: Path) -> bool:
        return not output.is_file() or output.stat().st_mtime < source.stat().st_mtime
