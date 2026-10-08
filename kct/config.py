"""Central configuration. Everything ING-specific comes from the environment.

Laravel analogy: this is config/app.php + .env. Never hardcode a project ID,
bucket or model name anywhere else in the codebase.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_id: str
    location: str
    model: str
    storage_root: Path
    prompts_root: Path
    temperature: float
    max_output_tokens: int

    @classmethod
    def from_env(cls) -> "Settings":
        base = Path(os.getenv("KCT_BASE_DIR", Path(__file__).resolve().parent.parent))
        return cls(
            project_id=os.environ.get("KCT_PROJECT_ID", ""),
            location=os.environ.get("KCT_LOCATION", "europe-west4"),
            model=os.environ.get("KCT_MODEL", "gemini-2.5-pro"),
            storage_root=Path(os.getenv("KCT_STORAGE_ROOT", base / "storage")),
            prompts_root=Path(os.getenv("KCT_PROMPTS_ROOT", base / "prompts")),
            # Deterministic by default: a control test must be reproducible.
            temperature=float(os.getenv("KCT_TEMPERATURE", "0")),
            max_output_tokens=int(os.getenv("KCT_MAX_OUTPUT_TOKENS", "8192")),
        )

    def require_project(self) -> str:
        if not self.project_id:
            raise RuntimeError(
                "KCT_PROJECT_ID is not set. Export it or put it in .env before calling Vertex."
            )
        return self.project_id


settings = Settings.from_env()
