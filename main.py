"""uvicorn main:app --host 0.0.0.0 --port 8000 --reload"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from routes.api import router
from services.ai.exceptions import AiConfigurationError
from services.control_testing.exceptions import InterpretationFailedError
from services.database.exceptions import DatabaseConfigurationError, RecordNotFoundError
from services.files.exceptions import CaseNotFoundError, InvalidUploadError

log = logging.getLogger("kct")

app = FastAPI(title="KCT", version="0.2.0")
app.include_router(router)


# Exception to HTTP status mapping (Laravel: app/Exceptions/Handler.php)
def _error(status: int, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(InvalidUploadError)
def invalid_upload(_: Request, exc: InvalidUploadError) -> JSONResponse:
    return _error(400, exc)


@app.exception_handler(CaseNotFoundError)
def case_not_found(_: Request, exc: CaseNotFoundError) -> JSONResponse:
    return _error(404, exc)


@app.exception_handler(RecordNotFoundError)
def record_not_found(_: Request, exc: RecordNotFoundError) -> JSONResponse:
    return _error(404, exc)


@app.exception_handler(DatabaseConfigurationError)
def database_misconfigured(_: Request, exc: DatabaseConfigurationError) -> JSONResponse:
    log.error("Database misconfigured: %s", exc)
    return _error(500, exc)


@app.exception_handler(AiConfigurationError)
def ai_misconfigured(_: Request, exc: AiConfigurationError) -> JSONResponse:
    log.error("AI misconfigured: %s", exc)
    return _error(500, exc)


@app.exception_handler(InterpretationFailedError)
def interpretation_failed(_: Request, exc: InterpretationFailedError) -> JSONResponse:
    log.error("%s", exc)
    return _error(502, exc)
