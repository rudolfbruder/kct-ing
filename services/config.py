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

    # Google Cloud (Gemini, and Claude when anthropic_platform is "vertex")
    gcp_project: str
    gemini_location: str
    anthropic_platform: str  # "vertex" (Claude on Vertex AI) or "api" (Anthropic API key)
    anthropic_region: str

    # Where uploads and outputs go: "local" (under storage_root) or "gcs".
    files_driver: str
    gcs_bucket: str
    gcs_prefix: str  # optional folder inside the bucket

    # Database: "sqlite" (local file) or "bigquery".
    db_driver: str
    db_path: Path  # SQLite file
    bq_dataset: str  # "dataset" in gcp_project, or "project.dataset"
    bq_location: str  # dataset location, e.g. EU or europe-west4; empty = BigQuery decides

    storage_root: Path
    prompts_root: Path
    fixtures_root: Path

    @property
    def logs_dir(self) -> Path:
        return self.storage_root / "logs"


@lru_cache(maxsize=1)
def settings() -> Settings:
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
        gcp_project=os.environ.get("KCT_PROJECT_ID", ""),
        gemini_location=os.environ.get("KCT_LOCATION", "europe-west4"),
        anthropic_platform=os.environ.get("KCT_ANTHROPIC_PLATFORM", "vertex").lower(),
        anthropic_region=os.environ.get("KCT_ANTHROPIC_REGION", "europe-west1"),
        files_driver=os.environ.get("KCT_FILES_DRIVER", "local").lower(),
        gcs_bucket=os.environ.get("KCT_GCS_BUCKET", ""),
        gcs_prefix=os.environ.get("KCT_GCS_PREFIX", ""),
        db_driver=os.environ.get("KCT_DB_DRIVER", "sqlite").lower(),
        db_path=Path(os.environ.get("KCT_DB_PATH", storage_root / "database.sqlite")),
        bq_dataset=os.environ.get("KCT_BQ_DATASET", ""),
        bq_location=os.environ.get("KCT_BQ_LOCATION", ""),
        storage_root=storage_root,
        prompts_root=Path(os.environ.get("KCT_PROMPTS_ROOT", BASE / "prompts")),
        fixtures_root=Path(os.environ.get("KCT_FIXTURES_ROOT", BASE / "tests" / "fixtures" / "fake_ai")),
    )
