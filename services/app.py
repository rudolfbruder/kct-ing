"""One place that builds every service, for the API and for notebooks alike.

Notebook (kernel in the project folder, or see notebooks/02_hello.ipynb):

    from services.app import boot
    kct = boot()                       # reads KCT_* env vars, sets up logging
    kct.ask.ask("What is 5+2?").answer
    kct.interpretations.create_and_generate(["CD.pdf"], ["TP.pdf"])
    kct.database.interpretations()

routes/api.py uses the same object, so API and notebook run identical code.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from bootstrap.logging import configure_logging
from services.config import settings
from services.control_testing.summary_service import SummaryService
from services.control_testing.interpretation_service import InterpretationService
from services.database import manager as database_manager
from services.database.contracts import CaseInterpretationRepository
from services.files.file_service import FileService
from services.playground.ask_service import AskService


@dataclass(frozen=True)
class App:
    files: FileService
    database: CaseInterpretationRepository
    summaries: SummaryService
    interpretations: InterpretationService
    ask: AskService


@lru_cache(maxsize=1)
def boot() -> App:
    configure_logging(settings())
    files = FileService()
    database = database_manager.repository()
    return App(
        files=files,
        database=database,
        summaries=SummaryService(files),
        interpretations=InterpretationService(files, database),
        ask=AskService(),
    )
