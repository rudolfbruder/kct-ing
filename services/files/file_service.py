"""Stores uploaded documents and generated outputs on the configured disk.

    uploads/<case_id>/<kind>/*.pdf    what the user uploaded
    outputs/<case_id>/*               what the agents produced

KCT_FILES_DRIVER picks the disk: "local" (under KCT_STORAGE_ROOT) or "gcs"
(in KCT_GCS_BUCKET). This class does not care which.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional

from services.ai.attachments import Document
from services.control_testing.data import DocumentKind
from services.files.disks.base import Disk
from services.files.disks.manager import disk as default_disk
from services.files.exceptions import CaseNotFoundError, InvalidUploadError

UPLOADS = "uploads"
OUTPUTS = "outputs"
# Empty file that claims a case number, so two uploads never get the same one.
CASE_MARKER = ".case"
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")


@dataclass(frozen=True)
class UploadedFile:
    name: str
    data: bytes


class FileService:
    def __init__(self, disk: Optional[Disk] = None) -> None:
        self.disk = disk or default_disk()

    def store_case(
        self,
        uploads: dict[DocumentKind, list[UploadedFile]],
        case_id: Optional[str] = None,
        name: str = "",
    ) -> str:
        """Saves the uploads as a case and returns its ID.

        Without case_id: a new numbered case (case-001, case-002, ...).
        With case_id (e.g. made from a control folder's name by case_id_from_name): that case,
        created if new; documents of the kinds uploaded replace the earlier ones. `name` is the
        human name kept with the case (the control folder's name).
        PDFs, and Markdown text (.md, e.g. a test plan that came as Excel), are accepted.
        """
        for kind, files in uploads.items():
            if not files:
                raise InvalidUploadError(f"No {kind.value} file uploaded")
            for file in files:
                if file.name.lower().endswith(".md"):
                    continue
                if not file.data.startswith(b"%PDF"):
                    raise InvalidUploadError(f"{kind.value}: {file.name} is not a PDF")

        if case_id is None:
            case_id = self._new_case_id()
            if name:
                self.disk.put(f"{UPLOADS}/{case_id}/{CASE_MARKER}", json.dumps({"name": name}).encode())
        else:
            if not CASE_ID.fullmatch(case_id):
                raise InvalidUploadError(f"Invalid case id {case_id!r}")
            self.disk.put(f"{UPLOADS}/{case_id}/{CASE_MARKER}", json.dumps({"name": name or case_id}).encode())
            for kind in uploads:
                for old in self.disk.files(f"{UPLOADS}/{case_id}/{kind.value}"):
                    self.disk.delete(f"{UPLOADS}/{case_id}/{kind.value}/{old}")
        for kind, files in uploads.items():
            for file in files:
                self.disk.put(f"{UPLOADS}/{case_id}/{kind.value}/{_safe_name(file.name)}", file.data)
        return case_id

    def case_name(self, case_id: str) -> str:
        """The human name of a case (a control folder's name), or its ID when it has none."""
        try:
            return json.loads(self.disk.get(f"{UPLOADS}/{case_id}/{CASE_MARKER}") or b"{}").get("name") or case_id
        except (FileNotFoundError, ValueError):
            return case_id

    def case_ids(self) -> list[str]:
        return self.disk.directories(UPLOADS)

    def document_names(self, case_id: str, kind: DocumentKind) -> list[str]:
        names = [n for n in self.disk.files(f"{UPLOADS}/{case_id}/{kind.value}")
                 if n.lower().endswith((".pdf", ".md"))]
        if not names:
            raise CaseNotFoundError(f"No {kind.value} documents for {case_id}")
        return names

    def documents(self, case_id: str, kind: DocumentKind) -> list[Document]:
        return [
            Document(
                data=self.disk.get(f"{UPLOADS}/{case_id}/{kind.value}/{name}"),
                title=f"{kind.label}: {name}",
                mime_type="text/plain" if name.lower().endswith(".md") else "application/pdf",
            )
            for name in self.document_names(case_id, kind)
        ]

    def save_output(self, case_id: str, filename: str, content) -> str:
        """Write an output file (text or bytes); returns its path on the disk."""
        path = f"{OUTPUTS}/{case_id}/{filename}"
        self.disk.put(path, content.encode("utf-8") if isinstance(content, str) else bytes(content))
        return path

    def read(self, path: str) -> bytes:
        """A file by the path save_output returned."""
        try:
            return self.disk.get(path)
        except Exception as exc:
            raise CaseNotFoundError(f"No file {path}") from exc

    def _new_case_id(self) -> str:
        numbers = [
            int(name.split("-", 1)[1])
            for name in self.case_ids()
            if name.startswith("case-") and name.split("-", 1)[1].isdigit()
        ]
        n = max(numbers, default=0) + 1
        while not self.disk.put(f"{UPLOADS}/case-{n:03d}/{CASE_MARKER}", b"", only_if_missing=True):
            n += 1  # another request took this number first
        return f"case-{n:03d}"


def _safe_name(name: str) -> str:
    # PurePosixPath(...).name drops any directory part a client sends in the filename.
    safe = PurePosixPath(name.replace("\\", "/")).name or "upload.pdf"
    return safe if safe.lower().endswith((".pdf", ".md")) else f"{safe}.pdf"


def case_id_from_name(name: str) -> str:
    """A case ID made from a human name, safe for folders and URLs.

    "5.0 Test of IAM resets (Q1)" -> "5.0-Test-of-IAM-resets-Q1"
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()   # č -> c, Ö -> O
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_name.strip()).strip("-.")
    slug = re.sub(r"-{2,}", "-", slug)[:80].strip("-.")
    if not slug:
        raise InvalidUploadError(f"Cannot make a case id from {name!r}")
    return slug
