"""EvidenceService: the evidence files the assessment will judge test steps against.

Evidence belongs to a case: <KCT_EVIDENCES_ROOT>/<case>/... (any subfolders).

    case = kct.evidences.case("case-002")      the evidence of one case
    case.store([UploadedFile(...)])            save uploads (API: POST /cases/{case}/evidences)
    case.units()                               one unit per uploaded file, converted for the AI
    case.parts()                               units split into parts that fit the model

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
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Optional, Union

from services.ai.attachments import MIME_TYPES, Document
from services.files.file_service import UploadedFile
from services.evidences.evidence_splitter import EvidencePart, EvidenceSplitter
from services.evidences.units import EVIDENCE_SUFFIXES, EvidenceUnit, document, evidence_kind, is_output
from services.evidences.docx_converter import DocxConversion, DocxConverter
from services.evidences.excel_converter import EXCEL_SUFFIXES, ExcelConversion, ExcelConverter
from services.evidences.exceptions import ConversionError, InvalidEvidenceError
from services.evidences.msg_converter import MsgConversion, MsgConverter

log = logging.getLogger("kct")

PathLike = Union[str, Path]


@dataclass(frozen=True)
class StoredEvidence:
    path: Path          # relative to the case's evidence folder
    size: int
    replaced: bool      # a file with this name was there and is overwritten


def _safe(name: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "_", name).strip(" .")
    return name or "evidence"


class EvidenceService:
    def __init__(
        self,
        root: Path,
        docx: Optional[DocxConverter] = None,
        excel: Optional[ExcelConverter] = None,
        msg: Optional[MsgConverter] = None,
        splitter: Optional[EvidenceSplitter] = None,
    ) -> None:
        self.root = Path(root)
        self.docx = docx or DocxConverter()
        self.excel = excel or ExcelConverter()
        self.msg = msg or MsgConverter(self.docx, self.excel)
        self.splitter = splitter or EvidenceSplitter()

    # --- cases -------------------------------------------------------------------------

    def case(self, case_id: str) -> "EvidenceService":
        """The same service, working in the evidence folder of one case."""
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", case_id) or case_id in (".", ".."):
            raise ConversionError(f"Invalid case id {case_id!r}")
        return EvidenceService(self.root / case_id, self.docx, self.excel, self.msg, self.splitter)

    def store(self, uploads: List[UploadedFile], folder: str = "") -> List[StoredEvidence]:
        """Save uploaded evidence files, optionally in a subfolder. Same name = replaced."""
        target = self.root
        for part in PurePosixPath(folder.replace("\\", "/")).parts:
            if part in ("", ".", "..", "/"):
                continue
            target = target / _safe(part)
        stored = []
        for upload in uploads:
            name = _safe(PurePosixPath(upload.name.replace("\\", "/")).name)
            if evidence_kind(Path(name)) is None:
                raise InvalidEvidenceError(
                    f"{upload.name}: not accepted as evidence; allowed: {', '.join(sorted(EVIDENCE_SUFFIXES))}")
            if not upload.data:
                raise InvalidEvidenceError(f"{upload.name}: the file is empty")
            if is_output(target / name):
                raise InvalidEvidenceError(f"{upload.name}: this name is reserved for converted files")
        target.mkdir(parents=True, exist_ok=True)
        for upload in uploads:
            path = target / _safe(PurePosixPath(upload.name.replace("\\", "/")).name)
            replaced = path.exists()
            path.write_bytes(upload.data)
            stored.append(StoredEvidence(path.relative_to(self.root), len(upload.data), replaced))
            log.info("evidence %s stored (%d bytes%s)", path, len(upload.data), ", replaced" if replaced else "")
        return stored

    def evidence_files(self) -> List[Path]:
        """The uploaded evidence files (relative paths), without what the converters made."""
        return [p for p in self.files() if evidence_kind(p) and not is_output(self.root / p)
                and not p.name.startswith("~$")]

    def units(self) -> List[EvidenceUnit]:
        """One unit per evidence file, converted for the AI. Conversions are refreshed."""
        return [self.unit(relative) for relative in self.evidence_files()]

    def unit(self, relative: PathLike) -> EvidenceUnit:
        relative = Path(relative)
        source = self.root / relative
        kind = evidence_kind(source)
        unit = EvidenceUnit(path=relative, kind=kind or "other")
        title = lambda p: str(p.relative_to(self.root))  # noqa: E731
        if kind == "word":
            unit.groups = [[document(self.convert_to_pdf(source).pdf, title(source.with_suffix(".pdf")))]]
        elif kind == "excel":
            result = self.convert_excel(source)
            unit.groups = [[document(f, title(f)) for f in [result.text, *result.images]]]
            if result.pdf:
                unit.groups.append([document(result.pdf, title(result.pdf))])
        elif kind == "email":
            result = self.convert_email(source)
            unit.anchor = document(result.text, title(result.text))
            for attachment in result.attachments:
                if attachment.outputs:
                    unit.groups.append([document(f, title(f)) for f in attachment.outputs])
                elif attachment.note:
                    unit.notes.append(f"{attachment.name}: {attachment.note}")
        elif kind in ("pdf", "image", "text"):
            unit.groups = [[document(source, title(source))]]
        else:
            raise ConversionError(f"{relative}: not an evidence file")
        return unit

    def parts(self, units: Optional[List[EvidenceUnit]] = None) -> List[EvidencePart]:
        """All units split into parts that fit the model (see EvidenceSplitter)."""
        return [part for unit in (units if units is not None else self.units()) for part in self.splitter.split(unit)]

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
