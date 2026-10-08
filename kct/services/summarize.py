"""Stage 1: summarize the control details and the test plan for a case.

Laravel analogy: an Action / Service class. The route calls this; this calls
storage, prompts and the model. No FastAPI imports here on purpose, so the same
code runs from the CLI, from a notebook and from a Cloud Run request.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from .. import gemini, prompts, storage
from ..config import settings
from ..models import DocumentKind, RunRecord, SummarizeResponse

PROMPT_FOR_KIND = {
    DocumentKind.CONTROL_DETAILS: "summarize_control_details",
    DocumentKind.TEST_PLAN: "summarize_test_plan",
}

UNSUPPORTED_HINT = (
    "Stage 1 accepts PDF, plain text and images. {name} is {mime}; convert it to "
    "PDF before uploading, or wait for the stage 2 extractors."
)


class UnsupportedSourceFile(Exception):
    pass


def output_name(kind: DocumentKind) -> str:
    return f"{kind.value}_summary.md"


def existing_summary(case_id: str, kind: DocumentKind) -> str | None:
    path = storage.output_dir(case_id) / output_name(kind)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def run(
    case_id: str,
    kind: DocumentKind,
    *,
    prompt_version: str | None = None,
    force: bool = False,
) -> SummarizeResponse:
    if kind not in PROMPT_FOR_KIND:
        raise ValueError(f"Stage 1 does not handle {kind.value}.")

    prompt = prompts.load(PROMPT_FOR_KIND[kind], prompt_version)

    if not force:
        cached = existing_summary(case_id, kind)
        if cached is not None:
            return SummarizeResponse(
                run_id="cached",
                case_id=case_id,
                kind=kind,
                output_path=str(storage.output_dir(case_id) / output_name(kind)),
                summary=cached,
                prompt_version=prompt.version,
                model=settings.model,
            )

    sources = storage.source_files(case_id, kind)
    for source in sources:
        if source.mime_type not in set(storage.NATIVE_MIME_TYPES.values()):
            raise UnsupportedSourceFile(
                UNSUPPORTED_HINT.format(name=source.filename, mime=source.mime_type)
            )

    parts = [
        gemini.file_part(storage.absolute_path(case_id, s.relative_path), s.mime_type)
        for s in sources
    ]
    parts.append(
        gemini.types.Part.from_text(
            text=(
                "Summarize the attached document(s) exactly as instructed. "
                f"Case: {case_id}. Files provided, in order: "
                + ", ".join(s.filename for s in sources)
            )
        )
    )

    run_id = uuid.uuid4().hex[:12]
    started = datetime.now(timezone.utc)
    error: str | None = None
    try:
        reply = gemini.generate(prompt.text, parts)
    except Exception as exc:  # recorded, then re-raised — a failed run is still a run
        error = f"{type(exc).__name__}: {exc}"
        reply = None
    finished = datetime.now(timezone.utc)

    summary = reply.text if reply else ""
    path = (
        storage.write_output(case_id, output_name(kind), summary)
        if reply
        else storage.output_dir(case_id) / output_name(kind)
    )

    record = RunRecord(
        run_id=run_id,
        case_id=case_id,
        kind=kind,
        model=settings.model,
        location=settings.location,
        temperature=settings.temperature,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        prompt_sha256=prompt.sha256,
        inputs=sources,
        output_path=str(path),
        output_sha256=hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        started_at=started,
        finished_at=finished,
        duration_ms=int((finished - started).total_seconds() * 1000),
        usage=reply.usage if reply else {},
        error=error,
    )
    storage.write_run_record(
        case_id, run_id, record.model_dump_json(indent=2)
    )

    if error:
        raise RuntimeError(error)

    return SummarizeResponse(
        run_id=run_id,
        case_id=case_id,
        kind=kind,
        output_path=str(path),
        summary=summary,
        prompt_version=prompt.version,
        model=settings.model,
    )
