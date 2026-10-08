"""HTTP surface. Laravel analogy: routes/api.php plus a thin controller.

Keep this file dumb: validate, call the service, map exceptions to status codes.
No business logic, no model calls.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from kct import prompts, storage
from kct.config import settings
from kct.models import (
    CaseManifest,
    DocumentKind,
    SourceFile,
    SummarizeRequest,
    SummarizeResponse,
)
from kct.services import summarize

router = APIRouter(prefix="/api/v1", tags=["kct"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": settings.model,
        "location": settings.location,
        "project_configured": bool(settings.project_id),
        "storage_root": str(settings.storage_root),
        "prompts": prompts.available(),
    }


@router.get("/cases", response_model=list[str])
def index_cases() -> list[str]:
    return storage.list_cases()


@router.get("/cases/{case_id}", response_model=CaseManifest)
def show_case(case_id: str) -> CaseManifest:
    try:
        return storage.read_manifest(case_id)
    except storage.CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cases/{case_id}/files/{kind}", response_model=list[SourceFile])
def list_files(case_id: str, kind: DocumentKind) -> list[SourceFile]:
    try:
        return storage.source_files(case_id, kind)
    except storage.CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except storage.NoSourceFiles as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cases/{case_id}/summarize", response_model=SummarizeResponse)
def summarize_document(case_id: str, payload: SummarizeRequest) -> SummarizeResponse:
    try:
        return summarize.run(
            case_id,
            payload.kind,
            prompt_version=payload.prompt_version,
            force=payload.force,
        )
    except storage.CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except storage.NoSourceFiles as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except prompts.PromptNotFound as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except summarize.UnsupportedSourceFile as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # The run record was already written, so the failure is auditable.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
