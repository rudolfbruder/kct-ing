"""One place that builds every service, for the API and for notebooks alike.

Notebook (kernel in the project folder, or see notebooks/02_hello.ipynb):

    from services.app import boot
    kct = boot()                       # reads KCT_* env vars, sets up logging
    kct.ask.ask("What is 5+2?").answer
    kct.interpretations.create_and_generate(["CD.pdf"], ["TP.pdf"])
    kct.evidences.case("case-001").store([...])
    kct.assessments.assess("case-001")
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
from services.assessment.assessment_service import AssessmentService
from services.importing.case_import_service import CaseImportService
from services.evidences.docx_converter import DocxConverter
from services.evidences.evidence_service import EvidenceService
from services.evidences.evidence_splitter import EvidenceSplitter
from services.evidences.excel_converter import ExcelConverter
from services.evidences.msg_converter import MsgConverter
from services.files.file_service import FileService
from services.playground.ask_service import AskService


@dataclass(frozen=True)
class App:
    files: FileService
    database: CaseInterpretationRepository
    summaries: SummaryService
    interpretations: InterpretationService
    ask: AskService
    evidences: EvidenceService
    assessments: AssessmentService
    importer: CaseImportService
    docx_converter: DocxConverter
    excel_converter: ExcelConverter
    msg_converter: MsgConverter


@lru_cache(maxsize=1)
def boot() -> App:
    configure_logging(settings())
    files = FileService()
    database = database_manager.repository()
    docx_converter = DocxConverter()
    excel_converter = ExcelConverter()
    msg_converter = MsgConverter(docx_converter, excel_converter)
    interpretations = InterpretationService(files, database)
    evidences = EvidenceService(settings().evidences_root, docx_converter, excel_converter, msg_converter,
                                EvidenceSplitter.from_settings(settings()))
    assessments = AssessmentService(files, database, evidences)
    return App(
        files=files,
        database=database,
        summaries=SummaryService(files),
        interpretations=interpretations,
        ask=AskService(),
        evidences=evidences,
        assessments=assessments,
        importer=CaseImportService(files, evidences, interpretations, assessments, docx_converter),
        docx_converter=docx_converter,
        excel_converter=excel_converter,
        msg_converter=msg_converter,
    )
