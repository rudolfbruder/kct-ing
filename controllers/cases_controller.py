"""Read-only views of stored cases, plus health."""
from __future__ import annotations

from typing import List

from services.config import settings
from services.control_testing.data import DocumentKind
from services.files.file_service import FileService


class CasesController:
    def __init__(self, files: FileService) -> None:
        self.files = files

    def health(self) -> dict:
        """GET /health"""
        config = settings()
        return {"status": "ok", "provider": config.ai_provider, "model": config.ai_model}

    def index(self) -> List[str]:
        """GET /cases"""
        return self.files.case_ids()

    def files_index(self, case_id: str, kind: DocumentKind) -> List[str]:
        """GET /cases/{case_id}/files/{kind}"""
        return self.files.document_names(case_id, kind)
