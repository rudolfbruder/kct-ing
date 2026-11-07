"""What counts as evidence, and which files the converters made next to it."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


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
