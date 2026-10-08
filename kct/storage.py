"""Filesystem layer for cases.

Laravel analogy: the Storage facade. Every path in the app is built here, so
swapping the local disk for GCS later means rewriting this file and nothing else.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .models import CaseManifest, DocumentKind, SourceFile

CASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{2,63}$")

# Gemini reads these natively. Anything else must be converted first (stage 2).
NATIVE_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".md": "text/plain",
    ".csv": "text/plain",
}


class CaseNotFound(Exception):
    pass


class NoSourceFiles(Exception):
    pass


def cases_root() -> Path:
    return settings.storage_root / "cases"


def validate_case_id(case_id: str) -> str:
    """Reject anything that could escape the storage root."""
    if not CASE_ID_RE.match(case_id):
        raise ValueError(
            f"Invalid case_id {case_id!r}: lowercase letters, digits, dash and underscore only."
        )
    return case_id


def case_dir(case_id: str) -> Path:
    path = cases_root() / validate_case_id(case_id)
    if not path.is_dir():
        raise CaseNotFound(f"No case folder at {path}")
    return path


def list_cases() -> list[str]:
    root = cases_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def read_manifest(case_id: str) -> CaseManifest:
    path = case_dir(case_id) / "case.json"
    if not path.is_file():
        return CaseManifest(case_id=case_id, created_at=datetime.now(timezone.utc))
    return CaseManifest.model_validate_json(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in NATIVE_MIME_TYPES:
        return NATIVE_MIME_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def describe_file(path: Path, base: Path) -> SourceFile:
    return SourceFile(
        filename=path.name,
        relative_path=str(path.relative_to(base)),
        mime_type=guess_mime(path),
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
    )


def source_files(case_id: str, kind: DocumentKind) -> list[SourceFile]:
    """Every file in storage/cases/<case_id>/<kind>/, sorted by name.

    Sorted so two runs over the same folder feed the model in the same order —
    otherwise the output is not reproducible.
    """
    base = case_dir(case_id)
    folder = base / kind.value
    if not folder.is_dir():
        raise NoSourceFiles(f"No {kind.value} folder in case {case_id}")

    files = sorted(
        (p for p in folder.rglob("*") if p.is_file() and not p.name.startswith(".")),
        key=lambda p: p.as_posix(),
    )
    if not files:
        raise NoSourceFiles(f"No files in {folder}")
    return [describe_file(p, base) for p in files]


def absolute_path(case_id: str, relative_path: str) -> Path:
    base = case_dir(case_id)
    resolved = (base / relative_path).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError("Path escapes the case folder.")
    return resolved


def output_dir(case_id: str) -> Path:
    path = case_dir(case_id) / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_output(case_id: str, name: str, content: str) -> Path:
    path = output_dir(case_id) / name
    path.write_text(content, encoding="utf-8")
    return path


def write_run_record(case_id: str, run_id: str, record_json: str) -> Path:
    runs = case_dir(case_id) / "output" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{run_id}.json"
    path.write_text(record_json, encoding="utf-8")
    return path


def bootstrap_case(case_id: str, manifest: CaseManifest | None = None) -> Path:
    """Create an empty case skeleton. Used by scripts and tests, not by the API."""
    validate_case_id(case_id)
    base = cases_root() / case_id
    for sub in ("control_details", "test_plan", "evidence", "output"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    manifest_path = base / "case.json"
    if manifest and not manifest_path.is_file():
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
    return base
