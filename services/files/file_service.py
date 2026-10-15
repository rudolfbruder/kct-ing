"""Stores uploaded documents and generated outputs on the configured disk.

    uploads/<case_id>/<kind>/*.pdf    what the user uploaded
    outputs/<case_id>/*               what the agents produced

KCT_FILES_DRIVER picks the disk: "local" (under KCT_STORAGE_ROOT) or "gcs"
(in KCT_GCS_BUCKET). This class does not care which.
"""
from __future__ import annotations

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


@dataclass(frozen=True)
class UploadedFile:
    name: str
    data: bytes


class FileService:
    def __init__(self, disk: Optional[Disk] = None) -> None:
        self.disk = disk or default_disk()

    def store_case(self, uploads: dict[DocumentKind, list[UploadedFile]]) -> str:
        """Saves the uploads as a new case and returns its ID (case-001, case-002, ...)."""
        for kind, files in uploads.items():
            if not files:
                raise InvalidUploadError(f"No {kind.value} file uploaded")
            for file in files:
                if not file.data.startswith(b"%PDF"):
                    raise InvalidUploadError(f"{kind.value}: {file.name} is not a PDF")

        case_id = self._new_case_id()
        for kind, files in uploads.items():
            for file in files:
                self.disk.put(f"{UPLOADS}/{case_id}/{kind.value}/{_safe_name(file.name)}", file.data)
        return case_id

    def case_ids(self) -> list[str]:
        return self.disk.directories(UPLOADS)

    def document_names(self, case_id: str, kind: DocumentKind) -> list[str]:
        names = [n for n in self.disk.files(f"{UPLOADS}/{case_id}/{kind.value}") if n.lower().endswith(".pdf")]
        if not names:
            raise CaseNotFoundError(f"No {kind.value} PDFs for {case_id}")
        return names

    def documents(self, case_id: str, kind: DocumentKind) -> list[Document]:
        return [
            Document(
                data=self.disk.get(f"{UPLOADS}/{case_id}/{kind.value}/{name}"),
                title=f"{kind.label}: {name}",
            )
            for name in self.document_names(case_id, kind)
        ]

    def save_output(self, case_id: str, filename: str, content: str) -> str:
        path = f"{OUTPUTS}/{case_id}/{filename}"
        self.disk.put(path, content.encode("utf-8"))
        return path

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
    return safe if safe.lower().endswith(".pdf") else f"{safe}.pdf"
