"""Application settings, read once from the environment (Laravel: config/*.php)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

DEFAULT_MODELS = {
    "fake": "fake",
    "gemini": "gemini-2.5-pro",
    "anthropic": "claude-opus-5-5",
}


@dataclass(frozen=True)
class Settings:
    # Which AI provider every agent uses unless the agent names its own:
    # "fake", "gemini" or "anthropic".
    ai_provider: str
    ai_model: str
    temperature: float
    # Output token limits per agent. On Gemini 2.5 and Claude, thinking counts against them.
    summary_max_tokens: int
    steps_max_tokens: int
    assessment_max_tokens: int   # per evidence part
    verdict_max_tokens: int      # the final verdict call

    # Google Cloud (Gemini, and Claude when anthropic_platform is "vertex")
    gcp_project: str
    gemini_location: str
    anthropic_platform: str  # "vertex" (Claude on Vertex AI) or "api" (Anthropic API key)
    anthropic_region: str

    # Where uploads and outputs go: "local" (under storage_root) or "gcs".
    files_driver: str
    gcs_bucket: str
    gcs_prefix: str  # optional folder inside the bucket

    # Database: "memory" (default, nothing stored), "sqlite" (local file) or "bigquery".
    db_driver: str
    db_path: Path  # SQLite file
    bq_dataset: str  # "dataset" in gcp_project, or "project.dataset"
    bq_location: str  # dataset location, e.g. EU or europe-west4; empty = BigQuery decides

    storage_root: Path
    # Evidence documents (assessment). Production layout unknown yet; default storage/evidences.
    evidences_root: Path
    # Folders the API may import from (POST /cases/import). Empty: the API cannot import.
    import_root: str
    zip_max_mb: int          # uncompressed size of an uploaded ZIP
    zip_max_files: int
    # Splitting evidence into parts the model reads well (see services/evidences/evidence_splitter.py).
    pdf_max_pages: int
    pdf_max_mb: float
    pdf_overlap_pages: int
    evidence_max_tokens: int
    # Brand on the report and dashboard; the logo file is never committed (see services/branding.py).
    brand_name: str
    brand_logo: Path
    prompts_root: Path
    fixtures_root: Path

    @property
    def logs_dir(self) -> Path:
        return self.storage_root / "logs"


def load_env_file(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env into the environment (no python-dotenv needed).

    Variables already set in the environment win, so a notebook cell or the
    shell can override .env. KCT_ENV_FILE picks another file; empty disables it.
    """
    if path is None:
        name = os.environ.get("KCT_ENV_FILE", str(BASE / ".env"))
        if not name:
            return
        path = Path(name)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


@lru_cache(maxsize=1)
def settings() -> Settings:
    load_env_file()
    provider = os.environ.get("KCT_AI_PROVIDER", "gemini").lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"KCT_AI_PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got {provider!r}")

    storage_root = Path(os.environ.get("KCT_STORAGE_ROOT", BASE / "storage"))

    return Settings(
        ai_provider=provider,
        ai_model=os.environ.get("KCT_AI_MODEL") or DEFAULT_MODELS[provider],
        temperature=float(os.environ.get("KCT_TEMPERATURE", "0")),
        summary_max_tokens=int(os.environ.get("KCT_SUMMARY_MAX_TOKENS", "16384")),
        steps_max_tokens=int(os.environ.get("KCT_STEPS_MAX_TOKENS", "32768")),
        assessment_max_tokens=int(os.environ.get("KCT_ASSESSMENT_MAX_TOKENS", "32768")),
        verdict_max_tokens=int(os.environ.get("KCT_VERDICT_MAX_TOKENS", "32768")),
        gcp_project=os.environ.get("KCT_PROJECT_ID", ""),
        gemini_location=os.environ.get("KCT_LOCATION", "europe-west4"),
        anthropic_platform=os.environ.get("KCT_ANTHROPIC_PLATFORM", "vertex").lower(),
        anthropic_region=os.environ.get("KCT_ANTHROPIC_REGION", "europe-west1"),
        files_driver=os.environ.get("KCT_FILES_DRIVER", "local").lower(),
        gcs_bucket=os.environ.get("KCT_GCS_BUCKET", ""),
        gcs_prefix=os.environ.get("KCT_GCS_PREFIX", ""),
        db_driver=os.environ.get("KCT_DB_DRIVER", "memory").lower(),
        db_path=Path(os.environ.get("KCT_DB_PATH", storage_root / "database.sqlite")),
        bq_dataset=os.environ.get("KCT_BQ_DATASET", ""),
        bq_location=os.environ.get("KCT_BQ_LOCATION", ""),
        storage_root=storage_root,
        evidences_root=Path(os.environ.get("KCT_EVIDENCES_ROOT", storage_root / "evidences")),
        import_root=os.environ.get("KCT_IMPORT_ROOT", ""),
        zip_max_mb=int(os.environ.get("KCT_ZIP_MAX_MB", "2048")),
        zip_max_files=int(os.environ.get("KCT_ZIP_MAX_FILES", "5000")),
        pdf_max_pages=int(os.environ.get("KCT_PDF_MAX_PAGES", "50")),
        pdf_max_mb=float(os.environ.get("KCT_PDF_MAX_MB", "20")),
        pdf_overlap_pages=int(os.environ.get("KCT_PDF_OVERLAP_PAGES", "2")),
        evidence_max_tokens=int(os.environ.get("KCT_EVIDENCE_MAX_TOKENS", "300000")),
        brand_name=os.environ.get("KCT_BRAND_NAME", "ING"),
        brand_logo=Path(os.environ.get("KCT_BRAND_LOGO", BASE / "branding" / "logo.png")),
        prompts_root=Path(os.environ.get("KCT_PROMPTS_ROOT", BASE / "prompts")),
        fixtures_root=Path(os.environ.get("KCT_FIXTURES_ROOT", BASE / "tests" / "fixtures" / "fake_ai")),
    )
