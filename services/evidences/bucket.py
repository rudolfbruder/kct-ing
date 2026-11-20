"""Bucket: one folder per converted document, holding the PDF and everything embedded in it.

    item = BucketConverter().convert(Path("EV-07.docx"), Path("storage/converted/20261120-1015"))
    item.folder          # storage/converted/20261120-1015/EV-07/        the bucket
    item.pdf             # .../EV-07/EV-07.pdf
    item.children        # the embedded files, each an item of its own

The layout of a bucket:

    EV-07/
      EV-07.pdf                     the document as PDF
      source/EV-07.docx             the original, unchanged
      attachments/                  the files embedded in the document, numbered in document order
        01_User list.xlsx           saved as it is (only Word is converted for now)
        02_Signed review.pdf        already a PDF
        03_Reviewer notes/          an embedded Word document: a bucket of its own (same layout),
          Reviewer notes.pdf          so its own embedded files are inside it
          source/...
          attachments/...
      manifest.json                 what is in the bucket and what happened to each file

A broken embedded file never fails the document; it is listed with the reason.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from services.evidences.docx_attachments import embedded_files
from services.evidences.docx_converter import DocxConverter

MAX_DEPTH = 3          # Word in Word in Word ...

# What happens to each kind of file.
CONVERTED = "converted"      # a PDF was made
PDF = "pdf"                  # it is a PDF already
SAVED = "saved"              # kept as it is; converting this format is not supported yet
FAILED = "failed"


@dataclass
class BucketItem:
    name: str                          # the file name (original, from the document when known)
    status: str                        # converted, pdf, saved, failed
    source: Optional[Path] = None      # the saved file
    pdf: Optional[Path] = None         # the PDF of it (for "pdf": the file itself)
    folder: Optional[Path] = None      # its bucket, for Word documents
    engine: str = ""
    error: str = ""
    children: List["BucketItem"] = field(default_factory=list)

    def walk(self):
        """This item and every item embedded in it, depth first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def as_dict(self, base: Optional[Path] = None) -> dict:
        def rel(path: Optional[Path]):
            if path is None:
                return None
            try:
                return path.relative_to(base).as_posix() if base else str(path)
            except ValueError:
                return str(path)
        return {"name": self.name, "status": self.status, "source": rel(self.source), "pdf": rel(self.pdf),
                "folder": rel(self.folder), "engine": self.engine, "error": self.error,
                "attachments": [child.as_dict(base) for child in self.children]}


def safe_name(name: str, default: str = "document") -> str:
    """A file name without folders or odd characters (Windows-safe)."""
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:150] or default


class BucketConverter:
    def __init__(self, docx: Optional[DocxConverter] = None) -> None:
        self.docx = docx or DocxConverter()

    def convert(self, source: Path, root: Path) -> BucketItem:
        """Make the bucket of one Word document under root (root/<document name>/)."""
        source = Path(source)
        return self.convert_bytes(source.name, source.read_bytes(), root)

    def convert_bytes(self, name: str, data: bytes, root: Path) -> BucketItem:
        """The same for an uploaded file (its name and bytes)."""
        folder = self._free(Path(root) / safe_name(Path(safe_name(name)).stem))
        return self._word(name, data, folder, depth=0)

    # --- one Word document -----------------------------------------------------------------

    def _word(self, name: str, data: bytes, folder: Path, depth: int) -> BucketItem:
        name = safe_name(name)
        (folder / "source").mkdir(parents=True, exist_ok=True)
        source = folder / "source" / name
        source.write_bytes(data)
        item = BucketItem(name=name, status=CONVERTED, source=source, folder=folder)
        try:
            done = self.docx.convert(source, pdf=folder / f"{Path(name).stem}.pdf")
            item.pdf, item.engine = done.pdf, done.engine
        except Exception as exc:   # the attachments may still be readable
            item.status, item.error = FAILED, f"{type(exc).__name__}: {exc}"
        try:
            attachments = embedded_files(source)
        except Exception as exc:
            attachments = []
            item.error = (item.error + "; " if item.error else "") + f"attachments not readable: {exc}"
        for number, attachment in enumerate(attachments, start=1):
            item.children.append(self._attachment(number, attachment, folder / "attachments", depth))
        self._manifest(item)
        return item

    def _attachment(self, number: int, attachment, folder: Path, depth: int) -> BucketItem:
        name = safe_name(attachment.name, default=f"attachment_{number}")
        numbered = f"{number:02d}_{name}"
        try:
            if attachment.suffix == ".docx" and depth + 1 < MAX_DEPTH:
                return self._word(name, attachment.data, folder / Path(numbered).stem, depth + 1)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / numbered
            path.write_bytes(attachment.data)
            if attachment.suffix == ".pdf":
                return BucketItem(name=name, status=PDF, source=path, pdf=path)
            note = "Word inside Word too deep, kept as it is" if attachment.suffix == ".docx" else \
                "kept as it is; converting this format is not supported yet"
            return BucketItem(name=name, status=SAVED, source=path, error=note)
        except Exception as exc:   # one bad attachment must not lose the rest
            return BucketItem(name=name, status=FAILED, error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _manifest(item: BucketItem) -> None:
        manifest = item.folder / "manifest.json"
        manifest.write_text(json.dumps(item.as_dict(item.folder), indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _free(folder: Path) -> Path:
        """folder, or folder_2, folder_3 ... when it is taken (two files with the same name)."""
        candidate, number = folder, 1
        while candidate.exists():
            number += 1
            candidate = folder.with_name(f"{folder.name}_{number}")
        return candidate
