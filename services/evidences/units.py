"""Evidence units: one uploaded file, with everything the AI gets for it.

An email is one unit together with its attachments, so the model sees that an
approval in the email belongs to the log attached to it.

    unit.path       the uploaded file, relative to the case's evidence folder
    unit.kind       word, excel, email, pdf, image or text
    unit.anchor     a document every part of the unit carries (the email text), or None
    unit.groups     documents that belong together; a group is never separated from
                    itself unless it alone is too big (an attachment's PDF + its text, a
                    workbook's text + its pictures)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from services.ai.attachments import MIME_TYPES, Document

# What may be uploaded as evidence.
EVIDENCE_SUFFIXES = {
    ".docx": "word",
    ".xlsx": "excel",
    ".xlsm": "excel",
    ".msg": "email",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".txt": "text",
    ".csv": "text",
}

# Files and folders the converters write next to the evidence; never evidence themselves.
OUTPUT_SUFFIXES = (".xlsx.md", ".xlsm.md", ".msg.md", ".xlsx.pdf", ".xlsm.pdf")
OUTPUT_FOLDER_SUFFIXES = (".xlsx_images", ".xlsm_images", ".msg_attachments")


def is_output(path: Path) -> bool:
    """True for files the converters made (and anything inside their folders)."""
    name = path.name.lower()
    if any(part.lower().endswith(OUTPUT_FOLDER_SUFFIXES) for part in path.parts[:-1]):
        return True
    if name.endswith(OUTPUT_SUFFIXES):
        return True
    return name.endswith(".pdf") and path.with_suffix(".docx").exists()


def evidence_kind(path: Path) -> Optional[str]:
    return EVIDENCE_SUFFIXES.get(path.suffix.lower())


def document(path: Path, title: str) -> Document:
    if path.suffix.lower() not in MIME_TYPES:
        raise ValueError(f"{path.name} is not readable by the models")
    return Document.from_path(path, title=title)


@dataclass
class EvidenceUnit:
    path: Path                      # relative to the case's evidence folder
    kind: str
    anchor: Optional[Document] = None
    groups: List[List[Document]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)   # e.g. attachments not sent

    @property
    def documents(self) -> List[Document]:
        return ([self.anchor] if self.anchor else []) + [d for group in self.groups for d in group]
