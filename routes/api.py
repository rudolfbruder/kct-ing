"""API routes. Laravel analogy: routes/api.php plus a thin controller."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kct import extractor

router = APIRouter(prefix="/api/v1")


class SummarizeRequest(BaseModel):
    case_id: str = "case-001"
    kind: str = "control_details"  # or "test_plan"


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "model": extractor.MODEL, "project": bool(extractor.PROJECT)}


@router.get("/cases")
def cases() -> list[str]:
    if not extractor.CASES.is_dir():
        return []
    return sorted(p.name for p in extractor.CASES.iterdir() if p.is_dir())


@router.get("/cases/{case_id}/files/{kind}")
def files(case_id: str, kind: str) -> list[str]:
    try:
        return [p.name for p in extractor.find_pdfs(case_id, kind)]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/summarize")
def summarize(payload: SummarizeRequest) -> dict:
    if payload.kind not in ("control_details", "test_plan"):
        raise HTTPException(status_code=400, detail="kind must be control_details or test_plan")
    try:
        text = extractor.summarize(payload.case_id, payload.kind)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc
    return {"case_id": payload.case_id, "kind": payload.kind, "summary": text}
