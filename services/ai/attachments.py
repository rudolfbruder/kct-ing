"""Files sent to a model along with the prompt (Laravel AI: Files\\Document)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    data: bytes
    title: str
    mime_type: str = "application/pdf"

    @classmethod
    def from_path(cls, path: Path, title: str = "") -> "Document":
        return cls(data=path.read_bytes(), title=title or path.name)
