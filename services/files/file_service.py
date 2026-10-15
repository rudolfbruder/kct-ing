"""Stores uploaded documents and generated outputs.

    storage/uploads/<case_id>/<kind>/*.pdf    what the user uploaded
    storage/outputs/<case_id>/*               what the agents produced
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from services.ai.attachments import Document
from services.config import Settings, settings
from services.control_testing.data import DocumentKind
from services.files.exceptions import CaseNotFoundError, InvalidUploadError


@dataclass(frozen=True)
class UploadedFile:
    name: str
    data: bytes


class FileService:
    def __init__(self, config: Optional[Settings] = None) -> None:
        config = config or settings()
        self.uploads = config.uploads_dir
        self.outputs = config.outputs_dir

    def store_case(self, uploads: dict[DocumentKind, list[UploadedFile]]) -> str:
        """Saves the uploads as a new case and returns its ID (case-001, case-002, ...)."""
        for kind, files in uploads.items():
            if not files:
                raise InvalidUploadError(f"No {kind.value} file uploaded")
            for file in files:
                if not file.data.startswith(b"%PDF"):
                    raise InvalidUploadError(f"{kind.value}: {file.name} is not a PDF")

        case_dir = self._new_case_dir()
        for kind, files in uploads.items():
            folder = case_dir / kind.value
            folder.mkdir()
            for file in files:
                (folder / _safe_name(file.name)).write_bytes(file.data)
        return case_dir.name

    def case_ids(self) -> list[str]:
        if not self.uploads.is_dir():
            return []
        return sorted(p.name for p in self.uploads.iterdir() if p.is_dir())

    def document_names(self, case_id: str, kind: DocumentKind) -> list[str]:
        return [p.name for p in self._pdfs(case_id, kind)]

    def documents(self, case_id: str, kind: DocumentKind) -> list[Document]:
        return [
            Document.from_path(p, title=f"{kind.label}: {p.name}") for p in self._pdfs(case_id, kind)
        ]

    def save_output(self, case_id: str, filename: str, content: str) -> Path:
        folder = self.outputs / case_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        path.write_text(content, encoding="utf-8")
        return path

    def read_output(self, case_id: str, filename: str) -> str:
        path = self.outputs / case_id / filename
        if not path.is_file():
            raise CaseNotFoundError(f"No {filename} for {case_id}")
        return path.read_text(encoding="utf-8")

    def _pdfs(self, case_id: str, kind: DocumentKind) -> list[Path]:
        folder = self.uploads / case_id / kind.value
        pdfs = sorted(folder.glob("*.pdf")) if folder.is_dir() else []
        if not pdfs:
            raise CaseNotFoundError(f"No {kind.value} PDFs for {case_id}")
        return pdfs

    def _new_case_dir(self) -> Path:
        self.uploads.mkdir(parents=True, exist_ok=True)
        numbers = [
            int(name.split("-", 1)[1])
            for name in self.case_ids()
            if name.startswith("case-") and name.split("-", 1)[1].isdigit()
        ]
        n = max(numbers, default=0) + 1
        while True:
            case_dir = self.uploads / f"case-{n:03d}"
            try:
                case_dir.mkdir()
                return case_dir
            except FileExistsError:  # another request took this number first
                n += 1


def _safe_name(name: str) -> str:
    # Path(...).name drops any directory part a client sends in the filename.
    safe = Path(name).name or "upload.pdf"
    return safe if safe.lower().endswith(".pdf") else f"{safe}.pdf"
