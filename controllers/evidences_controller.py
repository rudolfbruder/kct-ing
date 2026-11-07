"""Evidence of a case over HTTP. The work is done by EvidenceService."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import File, Form, UploadFile
from pydantic import BaseModel

from services.evidences.evidence_service import EvidenceService
from services.evidences.units import evidence_kind
from services.files.exceptions import CaseNotFoundError
from services.files.file_service import FileService, UploadedFile


class StoredEvidenceModel(BaseModel):
    path: str
    size: int
    replaced: bool


class EvidenceUploadResult(BaseModel):
    case_id: str
    stored: List[StoredEvidenceModel]
    evidence_count: int


class EvidenceFileModel(BaseModel):
    path: str
    kind: str
    size: int
    modified_at: str


class EvidencePartModel(BaseModel):
    unit: str
    label: str
    number: int
    total: int
    documents: List[str]
    estimated_tokens: int


class EvidencesController:
    def __init__(self, files: FileService, evidences: EvidenceService) -> None:
        self.files = files
        self.evidences = evidences

    def store(
        self,
        case_id: str,
        files: List[UploadFile] = File(...),
        folder: str = Form(""),
    ) -> EvidenceUploadResult:
        """POST /cases/{case_id}/evidences: upload evidence files (optionally into a subfolder)."""
        case = self._case(case_id)
        stored = case.store([UploadedFile(name=f.filename or "", data=f.file.read()) for f in files], folder)
        return EvidenceUploadResult(
            case_id=case_id,
            stored=[StoredEvidenceModel(path=str(s.path), size=s.size, replaced=s.replaced) for s in stored],
            evidence_count=len(case.evidence_files()),
        )

    def index(self, case_id: str) -> List[EvidenceFileModel]:
        """GET /cases/{case_id}/evidences: the uploaded evidence files."""
        case = self._case(case_id)
        out = []
        for relative in case.evidence_files():
            stat = case.path(relative).stat()
            out.append(EvidenceFileModel(
                path=str(relative), kind=evidence_kind(relative) or "other", size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            ))
        return out

    def parts(self, case_id: str) -> List[EvidencePartModel]:
        """GET /cases/{case_id}/evidences/parts: convert and split, as the assessment will send it."""
        case = self._case(case_id)
        return [
            EvidencePartModel(unit=p.unit, label=p.label, number=p.number, total=p.total,
                              documents=[d.title for d in p.documents], estimated_tokens=p.estimated_tokens)
            for p in case.parts()
        ]

    def _case(self, case_id: str) -> EvidenceService:
        if case_id not in self.files.case_ids():
            raise CaseNotFoundError(f"Unknown case {case_id}")
        return self.evidences.case(case_id)
