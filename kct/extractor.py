"""Stage 1: summarize a case's control details or test plan with Gemini.

Layout it expects:

    kct-ai/
      kct/extractor.py
      routes/api.py
      prompts/control_details.md
      prompts/test_plan.md
      storage/cases/case-001/control_details/*.pdf
      storage/cases/case-001/test_plan/*.pdf
      storage/cases/case-001/output/        (written here)
"""
from __future__ import annotations

import os
from pathlib import Path

from google import genai
from google.genai import types

BASE = Path(__file__).resolve().parent.parent
PROMPTS = BASE / "prompts"
CASES = BASE / "storage" / "cases"

PROJECT = os.environ.get("KCT_PROJECT_ID", "")
LOCATION = os.environ.get("KCT_LOCATION", "europe-west4")
MODEL = os.environ.get("KCT_MODEL", "gemini-2.5-pro")

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        if not PROJECT:
            raise RuntimeError("Set KCT_PROJECT_ID first.")
        _client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    return _client


def load_prompt(kind: str) -> str:
    path = PROMPTS / f"{kind}.md"
    if not path.is_file():
        raise FileNotFoundError(f"No prompt at {path}")
    return path.read_text(encoding="utf-8")


def find_pdfs(case_id: str, kind: str) -> list[Path]:
    folder = CASES / case_id / kind
    if not folder.is_dir():
        raise FileNotFoundError(f"No folder {folder}")
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs in {folder}")
    return pdfs


def summarize(case_id: str, kind: str) -> str:
    """kind is 'control_details' or 'test_plan'. Returns Markdown and writes it."""
    pdfs = find_pdfs(case_id, kind)
    parts = [
        types.Part.from_bytes(data=p.read_bytes(), mime_type="application/pdf")
        for p in pdfs
    ]
    parts.append(types.Part.from_text(text="Summarize the attached document(s)."))

    response = client().models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(
            system_instruction=load_prompt(kind),
            temperature=0,
            max_output_tokens=8192,
        ),
    )

    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    out_dir = CASES / case_id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{kind}_summary.md").write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    import sys

    case = sys.argv[1] if len(sys.argv) > 1 else "case-001"
    doc = sys.argv[2] if len(sys.argv) > 2 else "control_details"
    print(summarize(case, doc))
