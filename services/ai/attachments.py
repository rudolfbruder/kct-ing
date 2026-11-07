"""Files sent to a model along with the prompt (Laravel AI: Files\\Document)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# What Gemini and Claude accept as attachments, by file extension.
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/plain",
    ".csv": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class Document:
    data: bytes
    title: str
    mime_type: str = "application/pdf"

    @classmethod
    def from_path(cls, path: Path, title: str = "") -> "Document":
        path = Path(path)
        mime_type = MIME_TYPES.get(path.suffix.lower())
        if mime_type is None:
            raise ValueError(f"{path.name}: models accept {', '.join(sorted(MIME_TYPES))}; convert it first")
        return cls(data=path.read_bytes(), title=title or path.name, mime_type=mime_type)

    @property
    def is_text(self) -> bool:
        return self.mime_type.startswith("text/")

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")
