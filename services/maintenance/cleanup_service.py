"""CleanupService: delete what demos and test runs leave behind, safely.

    cleanup = CleanupService(settings())
    plan = cleanup.plan(["database", "cases", "evidence_outputs"])   # nothing deleted yet
    for target in plan: print(target)
    cleanup.run(plan)                                                # deletes exactly the plan

Groups:

    database          the SQLite file (KCT_DB_PATH) with all case interpretations and test steps
    cases             uploads/ and outputs/: every stored case and its readable results
    reports           the assessment PDFs (outputs/<case>/assessment_*.pdf)
    evidence_outputs  what the converters made in the evidences folder: PDFs next to .docx files,
                      .xlsx.md / .msg.md texts, *_images and *_attachments folders, Excel PDF copies
    evidence_samples  the fake evidence files from the factories (*_SAMPLE.*), case folders included
    evidence_all      EVERYTHING in the evidences folder, real evidence included
    demo_files        storage/demo/, sqlite_test.sqlite, api_from_notebook.log
    logs              storage/logs/ (app.log, agents.log)

Safety: only paths inside KCT_STORAGE_ROOT or KCT_EVIDENCES_ROOT are ever deleted, the
plan is shown before anything happens, and a BigQuery dataset or a GCS bucket is never
touched (those groups are skipped with a note).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from services.config import Settings
from services.evidences.units import is_output

GROUPS: Dict[str, str] = {
    "database": "SQLite database: all case interpretations and test steps",
    "cases": "Stored cases: uploads/ and outputs/",
    "reports": "Assessment reports: outputs/<case>/assessment_*.pdf",
    "evidence_outputs": "Converted evidence: PDFs from Word, texts and pictures from Excel and emails",
    "evidence_samples": "Fake evidence files from the factories (*_SAMPLE.*) and their outputs",
    "evidence_all": "EVERYTHING in the evidences folder, real evidence included",
    "demo_files": "Demo leftovers: storage/demo/, sqlite_test.sqlite, api_from_notebook.log",
    "logs": "Logs: storage/logs/",
}
OUTPUT_SUFFIXES = (".xlsx.md", ".xlsm.md", ".msg.md", ".xlsx.pdf", ".xlsm.pdf")
OUTPUT_FOLDERS = (".xlsx_images", ".xlsm_images", ".msg_attachments")


@dataclass(frozen=True)
class Target:
    group: str
    path: Path
    size: int           # bytes, folders included
    note: str = ""      # set when the target is skipped instead of deleted

    @property
    def skipped(self) -> bool:
        return bool(self.note)

    def __str__(self) -> str:
        what = "folder" if self.path.is_dir() else "file"
        if self.skipped:
            return f"[{self.group}] SKIPPED {self.path}: {self.note}"
        return f"[{self.group}] {what} {self.path} ({self.size / 1024:.1f} KB)"


class CleanupService:
    def __init__(self, config: Settings) -> None:
        self.config = config
        self.storage = Path(config.storage_root).resolve()
        self.evidences = Path(config.evidences_root).resolve()

    # --- planning ----------------------------------------------------------------------

    def plan(self, groups: Iterable[str]) -> List[Target]:
        """What would be deleted for these groups. Deletes nothing."""
        targets: Dict[Path, Target] = {}
        for group in groups:
            if group not in GROUPS:
                raise ValueError(f"Unknown group {group!r}; choose from {sorted(GROUPS)}")
            for target in getattr(self, f"_{group}")():
                # A folder already in the plan covers everything inside it.
                if not any(self._inside(target.path, other) for other in targets if other != target.path):
                    targets.setdefault(target.path, target)
        planned = sorted(targets.values(), key=lambda t: (t.group, str(t.path)))
        return [t for t in planned if not any(
            o.path != t.path and not o.skipped and self._inside(t.path, o.path) for o in planned)]

    def run(self, targets: Iterable[Target]) -> List[Target]:
        """Delete the planned targets. Returns what was deleted."""
        deleted = []
        for target in targets:
            if target.skipped or not target.path.exists():
                continue
            path = target.path.resolve()
            if not (self._inside(path, self.storage) or self._inside(path, self.evidences)):
                raise RuntimeError(f"Refusing to delete {path}: outside the storage and evidences folders")
            if path in (self.storage, self.evidences.parent) or path == Path(path.anchor):
                raise RuntimeError(f"Refusing to delete {path}: a root folder")
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted.append(target)
        return deleted

    # --- groups ------------------------------------------------------------------------

    def _database(self) -> List[Target]:
        driver = self.config.db_driver
        if driver == "bigquery":
            return [Target("database", Path(self.config.bq_dataset or "BigQuery dataset"), 0,
                           "BigQuery is never cleaned from here; drop the tables in the console")]
        if driver == "memory":
            return [Target("database", Path("(memory)"), 0,
                           "memory driver: nothing on disk; restart the kernel or the API to empty it")]
        db = Path(self.config.db_path).resolve()
        return [self._target("database", p) for p in (db, db.with_name(db.name + "-journal"),
                                                      db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm"))
                if p.exists()]

    def _cases(self) -> List[Target]:
        if self.config.files_driver == "gcs":
            return [Target("cases", Path(f"gs://{self.config.gcs_bucket}"), 0,
                           "GCS bucket is never cleaned from here")]
        return [self._target("cases", self.storage / name) for name in ("uploads", "outputs")
                if (self.storage / name).exists()]

    def _reports(self) -> List[Target]:
        if self.config.files_driver == "gcs":
            return [Target("reports", Path(f"gs://{self.config.gcs_bucket}"), 0, "GCS bucket is never cleaned from here")]
        outputs = self.storage / "outputs"
        return [self._target("reports", p) for p in sorted(outputs.glob("*/assessment_*.pdf"))] if outputs.is_dir() else []

    def _evidence_outputs(self) -> List[Target]:
        found = []
        if not self.evidences.is_dir():
            return found
        for path in sorted(self.evidences.rglob("*")):
            if any(self._inside(path, t.path) for t in found):
                continue
            name = path.name.lower()
            if path.is_dir() and name.endswith(OUTPUT_FOLDERS):
                found.append(self._target("evidence_outputs", path))
            elif path.is_file() and is_output(path):
                found.append(self._target("evidence_outputs", path))
        return found

    def _evidence_samples(self) -> List[Target]:
        """Factory files anywhere in the evidences folder (case folders too), not inside converter output."""
        if not self.evidences.is_dir():
            return []
        return [self._target("evidence_samples", p) for p in sorted(self.evidences.rglob("*_SAMPLE.*"))
                if p.is_file() and not is_output(p)]

    def _evidence_all(self) -> List[Target]:
        if not self.evidences.is_dir():
            return []
        return [self._target("evidence_all", p) for p in sorted(self.evidences.iterdir())]

    def _demo_files(self) -> List[Target]:
        names = ("demo", "sqlite_test.sqlite", "api_from_notebook.log")
        return [self._target("demo_files", self.storage / n) for n in names if (self.storage / n).exists()]

    def _logs(self) -> List[Target]:
        logs = self.storage / "logs"
        return [self._target("logs", logs)] if logs.exists() else []

    # --- helpers -----------------------------------------------------------------------

    @staticmethod
    def _target(group: str, path: Path) -> Target:
        path = path.resolve()
        size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else path.stat().st_size
        return Target(group, path, size)

    @staticmethod
    def _inside(path: Path, folder: Path) -> bool:
        try:
            path.resolve().relative_to(folder.resolve())
            return True
        except ValueError:
            return False
