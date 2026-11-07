"""CaseImportService: import a control folder in the SharePoint structure as a case.

The folder (OneDrive-synced or downloaded from SharePoint) looks like this:

    <control folder>/                     e.g. "5.0 Password resets of privileged accounts"
    └── Input/
        ├── Evidence/                     -> the case's evidence (subfolders kept)
        └── Test Plan and Control Details/ -> control details + test plan, in one folder

    result = kct.importer.import_folder("/home/jupyter/sharepoint/5.0 Password resets")
    result = kct.importer.import_folder(path, interpret=True, assess=True, progress=print)

What happens:
    1. The case ID is made from the control folder's name ("5.0-Password-resets-..."),
       the name itself is kept with the case. Importing the same folder again updates
       that case: new documents replace the old, a new interpretation/assessment is added.
    2. Every file in "Test Plan and Control Details" is converted (Word to PDF, Excel to
       text) and the AI decides whether it is the control details, the test plan or
       something else (DocumentClassifierAgent). `overrides` fixes a wrong decision by
       file name. At least one of each is required.
    3. "Evidence" is copied into the case's evidence folder, subfolders kept. By default
       the case's evidence is replaced (mirror), so files deleted in SharePoint go too.
    4. Optional: run the interpretation and then the assessment.

The source folder is only read: every conversion works on temporary copies, so nothing
is written into a OneDrive-synced folder (which would upload it to SharePoint).

    result = kct.importer.import_zip("OneDrive_1_2026-11-07.zip", interpret=True)

A ZIP is kept and sorted into storage/imports/<case>/ first (see import_zip), then
imported the same way.
"""
from __future__ import annotations

import io
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from services.ai.attachments import Document
from services.ai.exceptions import AiError
from services.config import settings
from services.control_testing.data import DocumentKind
from services.evidences.docx_converter import DocxConverter
from services.evidences.excel_converter import EXCEL_SUFFIXES, ExcelConverter
from services.evidences.evidence_service import EvidenceService
from services.evidences.units import evidence_kind
from services.files.file_service import FileService, UploadedFile, case_id_from_name
from services.importing.data import ClassifiedFile, ImportResult, SkippedFile
from services.importing.document_classifier_agent import DocumentClassifierAgent

log = logging.getLogger("kct")

Progress = Optional[Callable[[str], None]]
IGNORED = {".ds_store", "desktop.ini", "thumbs.db"}
DOCUMENT_SUFFIXES = (".pdf", ".docx", ".txt", ".md") + EXCEL_SUFFIXES


class ImportFolderError(Exception):
    """The folder is not a control folder, or the documents cannot be sorted."""


class CaseImportService:
    def __init__(self, files: FileService, evidences: EvidenceService, interpretations=None, assessments=None,
                 docx: Optional[DocxConverter] = None, excel: Optional[ExcelConverter] = None) -> None:
        self.files = files
        self.evidences = evidences
        self.interpretations = interpretations
        self.assessments = assessments
        self.docx = docx or DocxConverter()
        self.excel = excel or ExcelConverter(with_pdf=False)

    # --- public ----------------------------------------------------------------------

    def find_folders(self, path) -> Tuple[Path, Path, Path]:
        """(control folder, evidence folder, documents folder) for a control folder or its Input folder."""
        path = Path(path).expanduser()
        if not path.is_dir():
            raise ImportFolderError(f"{path} is not a folder")
        input_folder = _child(path, lambda n: n == "input")
        if input_folder is not None:
            control = path
        elif path.name.lower() == "input":
            control, input_folder = path.parent, path
        else:
            control = input_folder = path
        evidence = _child(input_folder, lambda n: "evidence" in n)
        documents = _child(input_folder, lambda n: "evidence" not in n and ("test plan" in n or "control" in n))
        if evidence is None or documents is None:
            found = ", ".join(sorted(p.name for p in input_folder.iterdir() if p.is_dir())) or "no folders"
            raise ImportFolderError(
                f'{input_folder} must contain an "Evidence" folder and a "Test Plan and Control Details" folder; '
                f"found: {found}")
        return control, evidence, documents

    def import_zip(self, zip_file, filename: str = "", case_name: str = "", interpret: bool = False,
                   assess: bool = False, progress: Progress = None) -> ImportResult:
        """One call from a ZIP (a path or its bytes) to a case.

        The ZIP is kept, unpacked and sorted into storage/imports/<case>/ in the SharePoint
        structure (Input/Evidence, Input/Test Plan and Control Details, other/) with an
        import.json of every decision, then imported like a folder. A ZIP that already has the
        structure is sorted by its folders; a flat ZIP is sorted file by file by the AI
        (control details, test plan, evidence or other). The case is named after case_name, or
        the folder the ZIP wraps everything in, or the ZIP's file name.
        """
        if isinstance(zip_file, (bytes, bytearray)):
            data, filename = bytes(zip_file), filename or "upload.zip"
        else:
            data, filename = Path(zip_file).read_bytes(), filename or Path(zip_file).name
        config = settings()
        importer = ZipImporter(self, config.storage_root / "imports", config.zip_max_mb, config.zip_max_files)
        return importer.run(data, filename, case_name, interpret, assess, progress or (lambda message: None))

    def import_folder(self, path, overrides: Optional[Dict[str, str]] = None, mirror: bool = True,
                      interpret: bool = False, assess: bool = False, progress: Progress = None,
                      case_name: str = "") -> ImportResult:
        say = progress or (lambda message: None)
        control, evidence_folder, documents_folder = self.find_folders(path)
        case_name = case_name or control.name
        case_id = case_id_from_name(case_name)
        say(f'Control folder "{case_name}" -> case {case_id}')

        with tempfile.TemporaryDirectory(prefix="kct-import-") as work:
            classified, skipped, uploads, extra_evidence = self._documents(
                documents_folder, Path(work), overrides or {}, say)
        result = ImportResult(
            case_id=case_id, case_name=case_name, source=str(control),
            control_details=[c for c in classified if c.role == "control_details"],
            test_plan=[c for c in classified if c.role == "test_plan"],
            other=[c for c in classified if c.role == "other"], skipped=skipped,
        )
        if not result.control_details or not result.test_plan:
            missing = " and ".join(n for n, f in (("control details", result.control_details),
                                                 ("a test plan", result.test_plan)) if not f)
            decided = "; ".join(f"{c.name}: {c.role}" for c in classified) or "no readable files"
            raise ImportFolderError(
                f"No {missing} found in {documents_folder.name} ({decided}). "
                'Fix a wrong decision with overrides={"file name": "control_details" | "test_plan"}.')

        self.files.store_case(
            {DocumentKind.CONTROL_DETAILS: uploads["control_details"], DocumentKind.TEST_PLAN: uploads["test_plan"]},
            case_id=case_id, name=case_name,
        )
        say(f"Stored {len(result.control_details)} control details and {len(result.test_plan)} test plan file(s)")

        result.evidence, ev_skipped, result.removed_evidence = self._evidence(case_id, evidence_folder, mirror)
        result.skipped += ev_skipped
        for source in extra_evidence:   # sorted as evidence although it sat with the documents
            for item in self.evidences.case(case_id).store([UploadedFile(name=source.name, data=source.read_bytes())]):
                result.evidence.append(str(item.path))
                if str(item.path) in result.removed_evidence:
                    result.removed_evidence.remove(str(item.path))
        say(f"Copied {len(result.evidence)} evidence file(s)"
            + (f", removed {len(result.removed_evidence)} no longer in the folder" if result.removed_evidence else "")
            + (f", skipped {len(ev_skipped)}" if ev_skipped else ""))
        log.info("%s: imported from %s (%d evidence files)", case_id, control, len(result.evidence))

        if interpret or assess:
            say("Interpretation: summaries and test steps ...")
            interpretation = self.interpretations.generate(case_id)
            result.case_interpretation_id = interpretation.metadata.case_interpretation_id
            say(f"✅ {len(interpretation.test_steps)} test steps")
        if assess:
            assessment = self.assessments.assess(case_id, result.case_interpretation_id, progress=say)
            result.assessment_id = assessment.metadata.assessment_id
        return result

    # --- documents ---------------------------------------------------------------------

    def _documents(self, folder: Path, work: Path, overrides: Dict[str, str], say):
        classified: List[ClassifiedFile] = []
        skipped: List[SkippedFile] = []
        uploads: Dict[str, List[UploadedFile]] = {"control_details": [], "test_plan": [], "evidence": [], "other": []}
        extra_evidence: List[Path] = []
        for source in _files(folder):
            relative = str(source.relative_to(folder))
            if source.suffix.lower() not in DOCUMENT_SUFFIXES:
                skipped.append(SkippedFile(path=f"{folder.name}/{relative}",
                                           reason=f"{source.suffix or 'no extension'} is not a readable document"))
                continue
            try:
                upload, document = self._readable(source, work)
            except Exception as exc:  # a broken file must not stop the import
                skipped.append(SkippedFile(path=f"{folder.name}/{relative}", reason=f"cannot be read: {exc}"))
                continue
            role = overrides.get(source.name) or overrides.get(relative)
            if role:
                if role not in ("control_details", "test_plan", "evidence", "other"):
                    raise ImportFolderError(
                        f"Override for {source.name} must be control_details, test_plan, evidence or other")
                item = ClassifiedFile(name=relative, role=role, reason="set by hand", by="override")
            else:
                say(f"Sorting {relative} ...")
                try:
                    answer = self.classify(f"{folder.name}/{relative}", document)
                    item = ClassifiedFile(name=relative, role=answer.role, reason=answer.reason)
                except AiError as exc:
                    skipped.append(SkippedFile(path=f"{folder.name}/{relative}", reason=f"could not be sorted: {exc}"))
                    continue
            say(f"   {relative}: {item.role.replace('_', ' ')} ({item.reason})")
            classified.append(item)
            uploads[item.role].append(upload)
            if item.role == "evidence":
                extra_evidence.append(source)
        return classified, skipped, uploads, extra_evidence

    def classify(self, path: str, document: Document):
        """Ask the AI for one file's role. Only the start of a big file is sent."""
        return DocumentClassifierAgent().prompt(
            f"Path in the upload: {path}\nWhat is this document's role?", attachments=[_preview(document)]).structured

    def _readable(self, source: Path, work: Path) -> Tuple[UploadedFile, Document]:
        """The file as the interpretation reads it: PDF as is, Word as PDF, Excel and text as Markdown."""
        suffix = source.suffix.lower()
        copy = work / source.name
        shutil.copy2(source, copy)          # never convert inside the (synced) source folder
        if suffix == ".pdf":
            data, name, mime = copy.read_bytes(), source.name, "application/pdf"
        elif suffix == ".docx":
            data, name, mime = self.docx.convert(copy).pdf.read_bytes(), f"{source.stem}.pdf", "application/pdf"
        elif suffix in EXCEL_SUFFIXES:
            data, name, mime = self.excel.convert(copy).text.read_bytes(), f"{source.name}.md", "text/plain"
        else:
            data, name, mime = copy.read_bytes(), f"{source.stem}.md", "text/plain"
        return UploadedFile(name=name, data=data), Document(data=data, title=name, mime_type=mime)

    # --- evidence ----------------------------------------------------------------------

    def _evidence(self, case_id: str, folder: Path, mirror: bool):
        case = self.evidences.case(case_id)
        before = {str(p) for p in case.evidence_files()}
        if mirror and case.root.exists():
            shutil.rmtree(case.root)
        stored: List[str] = []
        skipped: List[SkippedFile] = []
        for source in _files(folder):
            relative = source.relative_to(folder)
            if evidence_kind(source) is None:
                skipped.append(SkippedFile(path=f"{folder.name}/{relative}",
                                           reason=f"{source.suffix or 'no extension'} is not accepted as evidence"))
                continue
            if source.stat().st_size == 0:
                skipped.append(SkippedFile(path=f"{folder.name}/{relative}", reason="empty file"))
                continue
            for item in case.store([UploadedFile(name=source.name, data=source.read_bytes())],
                                   folder=str(relative.parent).replace("\\", "/") if str(relative.parent) != "." else ""):
                stored.append(str(item.path))
        removed = sorted(before - set(stored)) if mirror else []
        return stored, skipped, removed


PREVIEW_PAGES = 3
PREVIEW_CHARS = 30_000


def _preview(document: Document) -> Document:
    """The first pages of a PDF or the first characters of a text: enough to tell what a file is."""
    if document.mime_type == "application/pdf":
        try:
            import io

            from pypdf import PdfReader, PdfWriter

            reader = PdfReader(io.BytesIO(document.data))
            if len(reader.pages) <= PREVIEW_PAGES:
                return document
            writer = PdfWriter()
            for page in reader.pages[:PREVIEW_PAGES]:
                writer.add_page(page)
            buffer = io.BytesIO()
            writer.write(buffer)
            return Document(data=buffer.getvalue(), title=f"{document.title} (first {PREVIEW_PAGES} pages)",
                            mime_type=document.mime_type)
        except Exception:
            return document
    if document.is_text and len(document.data) > PREVIEW_CHARS:
        return Document(data=document.data[:PREVIEW_CHARS], title=f"{document.title} (beginning)",
                        mime_type=document.mime_type)
    return document


def _child(folder: Path, test) -> Optional[Path]:
    matches = sorted(p for p in folder.iterdir() if p.is_dir() and test(p.name.lower().strip()))
    return matches[0] if matches else None


def _files(folder: Path) -> List[Path]:
    """Files below a folder, sorted; skips Office lock files, system files and hidden files."""
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and not p.name.startswith(("~$", ".")) and p.name.lower() not in IGNORED
        and not any(part.startswith(".") for part in p.relative_to(folder).parts[:-1])
    )


# --- ZIP ------------------------------------------------------------------------------------

class ZipImporter:
    """import_zip(): one call from an uploaded ZIP to a case. Used by CaseImportService.import_zip."""

    def __init__(self, service: "CaseImportService", imports_root: Path, max_mb: int, max_files: int) -> None:
        self.service = service
        self.imports_root = Path(imports_root)
        self.max_bytes = max_mb * 1024 * 1024
        self.max_files = max_files

    def run(self, data: bytes, filename: str, case_name: str, interpret: bool, assess: bool, say) -> ImportResult:
        import datetime
        import json
        import zipfile

        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ImportFolderError(f"{filename} is not a ZIP file") from exc

        with tempfile.TemporaryDirectory(prefix="kct-zip-") as work:
            extracted = Path(work) / "extracted"
            self._extract(archive, extracted)
            top = self._top(extracted)
            name = case_name or (top.name if top != extracted else Path(filename).stem)
            case_id = case_id_from_name(name)
            target = self.imports_root / case_id
            say(f'ZIP {filename} -> case "{name}" ({case_id})')

            # Fresh sorted copy for this import; earlier source ZIPs are kept.
            for folder in ("Input", "other"):
                if (target / folder).exists():
                    shutil.rmtree(target / folder)
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            source_zip = target / "source" / f"{stamp}_{_safe_file(filename)}"
            source_zip.parent.mkdir(parents=True, exist_ok=True)
            source_zip.write_bytes(data)

            evidence_dir = target / "Input" / "Evidence"
            documents_dir = target / "Input" / "Test Plan and Control Details"
            evidence_dir.mkdir(parents=True)
            documents_dir.mkdir(parents=True)
            sorted_by_ai: List[ClassifiedFile] = []
            skipped: List[SkippedFile] = []
            overrides: Dict[str, str] = {}

            try:
                _, src_evidence, src_documents = self.service.find_folders(top)
                say("SharePoint structure found: the folders decide what is evidence")
                junk = shutil.ignore_patterns(".*", "~$*", "Thumbs.db", "desktop.ini", "__MACOSX")
                shutil.copytree(src_evidence, evidence_dir, dirs_exist_ok=True, ignore=junk)
                shutil.copytree(src_documents, documents_dir, dirs_exist_ok=True, ignore=junk)
            except ImportFolderError:
                say("No folder structure: the AI sorts every file")
                sorted_by_ai, skipped, overrides = self._sort_flat(top, Path(work), evidence_dir, documents_dir,
                                                                   target / "other", say)

        result = self.service.import_folder(target, overrides=overrides, interpret=interpret, assess=assess,
                                            progress=say, case_name=name)
        result.source_zip = str(source_zip)
        result.sorted_folder = str(target)
        result.sorted_by_ai = sorted_by_ai
        result.skipped = skipped + result.skipped
        (target / "import.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    def _sort_flat(self, top: Path, work: Path, evidence_dir: Path, documents_dir: Path, other_dir: Path, say):
        decisions: List[ClassifiedFile] = []
        skipped: List[SkippedFile] = []
        overrides: Dict[str, str] = {}
        for source in _files(top):
            relative = source.relative_to(top)
            readable = source.suffix.lower() in DOCUMENT_SUFFIXES or evidence_kind(source) is not None
            if not readable:
                destination = other_dir / relative
                decisions.append(ClassifiedFile(name=str(relative), role="other",
                                                reason=f"{source.suffix or 'no extension'} cannot be read"))
            else:
                try:
                    document = self._document(source, work)
                    say(f"Sorting {relative} ...")
                    answer = self.service.classify(str(relative), document)
                    item = ClassifiedFile(name=str(relative), role=answer.role, reason=answer.reason)
                except Exception as exc:  # unreadable or the AI failed: keep it, but out of the case
                    item = ClassifiedFile(name=str(relative), role="other", reason=f"could not be sorted: {exc}")
                decisions.append(item)
                say(f"   {relative}: {item.role.replace('_', ' ')} ({item.reason})")
                if item.role == "evidence":
                    destination = evidence_dir / relative
                elif item.role in ("control_details", "test_plan"):
                    destination = documents_dir / relative
                    overrides[str(relative)] = item.role
                else:
                    destination = other_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return decisions, skipped, overrides

    def _document(self, source: Path, work: Path) -> Document:
        """A readable version for sorting: documents as for the interpretation, evidence via its converter."""
        if source.suffix.lower() in DOCUMENT_SUFFIXES:
            return self.service._readable(source, work)[1]
        copy = work / "sort" / source.name
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy)
        if source.suffix.lower() == ".msg":
            from services.evidences.msg_converter import MsgConverter

            text = MsgConverter(self.service.docx, self.service.excel).convert(copy).text
            return Document(data=text.read_bytes(), title=f"{source.name}.md", mime_type="text/plain")
        return Document.from_path(copy, title=source.name)

    def _extract(self, archive, target: Path) -> None:
        entries = [i for i in archive.infolist() if not i.is_dir()]
        if len(entries) > self.max_files:
            raise ImportFolderError(f"The ZIP has {len(entries)} files; the limit is {self.max_files} (KCT_ZIP_MAX_FILES)")
        total = sum(i.file_size for i in entries)
        if total > self.max_bytes:
            raise ImportFolderError(f"The ZIP unpacks to {total / 1024 / 1024:.0f} MB; the limit is "
                                    f"{self.max_bytes // 1024 // 1024} MB (KCT_ZIP_MAX_MB)")
        root = target.resolve()
        for info in entries:
            if info.flag_bits & 0x1:
                raise ImportFolderError(f"The ZIP is password-protected ({info.filename}); upload it without a password")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                continue  # symbolic link: never follow
            if info.compress_size and info.file_size / info.compress_size > 200 and info.file_size > 50 * 1024 * 1024:
                raise ImportFolderError(f"{info.filename} looks like a ZIP bomb (compression ratio over 200)")
            name = _zip_name(info)
            path = (target / name).resolve()
            if root not in path.parents:
                raise ImportFolderError(f"The ZIP contains a path outside its folder: {name}")
            if any(part.startswith("__MACOSX") for part in Path(name).parts):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(path, "wb") as out:
                shutil.copyfileobj(source, out)

    @staticmethod
    def _top(folder: Path) -> Path:
        """The single folder a ZIP often wraps everything in (e.g. a SharePoint download), else the root."""
        current = folder
        while True:
            children = [p for p in current.iterdir() if not p.name.startswith(".")]
            if len(children) == 1 and children[0].is_dir() and children[0].name.lower() != "input":
                current = children[0]
            else:
                return current


def _zip_name(info) -> str:
    """The entry's name; ZIPs made on Windows without the UTF-8 flag store names in cp437."""
    name = info.filename
    if not info.flag_bits & 0x800:
        try:
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name.replace("\\", "/")


def _safe_file(name: str) -> str:
    import re

    return re.sub(r"[^\w.\- ]+", "_", Path(name.replace("\\", "/")).name).strip(" .") or "upload.zip"
