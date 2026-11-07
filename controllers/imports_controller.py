"""Import a control folder (SharePoint structure) over HTTP. The work is done by CaseImportService."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from fastapi import BackgroundTasks, File, Form, UploadFile
from pydantic import BaseModel

from services.assessment.assessment_service import AssessmentService
from services.config import settings
from services.importing.case_import_service import CaseImportService, ImportFolderError
from services.importing.data import ImportResult


class ImportRequest(BaseModel):
    path: str                                   # inside KCT_IMPORT_ROOT
    overrides: Dict[str, str] = {}              # {"file name": "control_details" | "test_plan" | "other"}
    mirror: bool = True                         # the case's evidence = exactly the folder's evidence
    interpret: bool = False                     # also run the interpretation (waits for it)
    assess: bool = False                        # also start the assessment in the background (implies interpret)


class ImportsController:
    def __init__(self, importer: CaseImportService, assessments: AssessmentService) -> None:
        self.importer = importer
        self.assessments = assessments

    def store(self, payload: ImportRequest, background: BackgroundTasks) -> ImportResult:
        """POST /cases/import: import a control folder from the workbench's disk as a case."""
        path = self._allowed(payload.path)
        result = self.importer.import_folder(path, payload.overrides, payload.mirror,
                                             interpret=payload.interpret or payload.assess)
        if payload.assess:
            metadata = self.assessments.start(result.case_id, result.case_interpretation_id)
            background.add_task(self.assessments.run, metadata.assessment_id)
            result.assessment_id = metadata.assessment_id
        return result

    @staticmethod
    def _allowed(raw: str) -> Path:
        root: Optional[str] = settings().import_root
        if not root:
            raise ImportFolderError("Importing through the API is off: set KCT_IMPORT_ROOT to the folder "
                                    "that holds the control folders")
        path = Path(raw).expanduser().resolve()
        base = Path(root).expanduser().resolve()
        if path != base and base not in path.parents:
            raise ImportFolderError(f"{raw} is outside KCT_IMPORT_ROOT ({base})")
        return path

    def store_zip(
        self,
        background: BackgroundTasks,
        file: UploadFile = File(...),
        case_name: str = Form(""),
        interpret: bool = Form(False),
        assess: bool = Form(False),
    ) -> ImportResult:
        """POST /cases/import-zip: upload a ZIP; it is kept, sorted per case and imported."""
        result = self.importer.import_zip(file.file.read(), file.filename or "upload.zip", case_name,
                                          interpret=interpret or assess)
        if assess:
            metadata = self.assessments.start(result.case_id, result.case_interpretation_id)
            background.add_task(self.assessments.run, metadata.assessment_id)
            result.assessment_id = metadata.assessment_id
        return result
