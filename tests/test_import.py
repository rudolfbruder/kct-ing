"""Importing a control folder in the SharePoint structure (fake AI)."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from factories import ControlFolderFactory
from factories.control_folder_factory import CONTROL_DETAILS, TEST_PLAN
from services.control_testing.data import DocumentKind
from services.evidences.docx_converter import DocxConverter
from services.evidences.evidence_service import EvidenceService
from services.files.disks.local import LocalDisk
from services.files.file_service import FileService, case_id_from_name
from services.importing.case_import_service import CaseImportService, ImportFolderError
from services.importing.document_classifier_agent import DocumentClassifierAgent

CD = '{"role": "control_details", "reason": "describes the control"}'
TP = '{"role": "test_plan", "reason": "lists test steps"}'


def snapshot(folder: Path) -> dict:
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


class ImportTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="kct-import-test-"))
        self.source = ControlFolderFactory(excel_rows=10, pdf_pages=3).create(root / "sharepoint")
        self.files = FileService(LocalDisk(root / "storage"))
        self.evidences = EvidenceService(root / "storage" / "evidences", docx=DocxConverter("python"))
        self.importer = CaseImportService(self.files, self.evidences, docx=DocxConverter("python"))

    def run_import(self, answers=(CD, TP), **kwargs):
        DocumentClassifierAgent.fake(list(answers))
        try:
            return self.importer.import_folder(self.source, **kwargs)
        finally:
            DocumentClassifierAgent.stop_faking()

    def test_imports_documents_and_evidence_without_touching_the_source(self) -> None:
        before = snapshot(self.source)
        result = self.run_import()
        self.assertEqual(snapshot(self.source), before)                     # nothing written into the synced folder

        self.assertEqual(result.case_id, case_id_from_name(ControlFolderFactory.name))
        self.assertEqual(self.files.case_name(result.case_id), ControlFolderFactory.name)
        self.assertEqual([c.name for c in result.control_details], [CONTROL_DETAILS])
        self.assertEqual([c.name for c in result.test_plan], [TEST_PLAN])
        # Word control details were converted to PDF for the interpretation
        self.assertEqual(self.files.document_names(result.case_id, DocumentKind.CONTROL_DETAILS),
                         [CONTROL_DETAILS.replace(".docx", ".pdf")])
        self.assertEqual(sorted(result.evidence), sorted([
            "EV-01_password_reset_tickets_SAMPLE.docx", "EV-04_evidence_email_SAMPLE.msg",
            "EV-05_service_desk_log_export_SAMPLE.pdf", "Q1 2026/EV-03_ADX_audit_log_extract_SAMPLE.xlsx"]))
        self.assertEqual([s.path for s in result.skipped], ["Evidence/meeting notes.pptx"])   # lock/.DS_Store ignored

    def test_reimport_replaces_and_mirrors(self) -> None:
        first = self.run_import()
        (self.source / "Input" / "Evidence" / "EV-05_service_desk_log_export_SAMPLE.pdf").unlink()
        second = self.run_import()
        self.assertEqual(second.case_id, first.case_id)
        self.assertEqual(second.removed_evidence, ["EV-05_service_desk_log_export_SAMPLE.pdf"])
        self.assertNotIn("EV-05_service_desk_log_export_SAMPLE.pdf",
                         [str(p) for p in self.evidences.case(first.case_id).evidence_files()])
        self.assertEqual(len(self.files.document_names(first.case_id, DocumentKind.TEST_PLAN)), 1)   # replaced

    def test_wrong_sorting_is_reported_and_can_be_overridden(self) -> None:
        with self.assertRaises(ImportFolderError) as raised:
            self.run_import(answers=(CD, CD))
        self.assertIn("No a test plan found", str(raised.exception))
        result = self.run_import(answers=(CD,), overrides={TEST_PLAN: "test_plan"})
        self.assertEqual(result.test_plan[0].by, "override")

    def test_accepts_the_input_folder_and_rejects_other_folders(self) -> None:
        control, evidence, documents = self.importer.find_folders(self.source / "Input")
        self.assertEqual(control, self.source)
        self.assertEqual(evidence.name, "Evidence")
        with self.assertRaises(ImportFolderError):
            self.importer.find_folders(self.source / "Input" / "Evidence")

    def test_case_ids_from_names(self) -> None:
        self.assertEqual(case_id_from_name("5.0 Test of resets (Q1)"), "5.0-Test-of-resets-Q1")
        self.assertEqual(case_id_from_name("Kontrola č. 7 Überprüfung"), "Kontrola-c.-7-Uberprufung")



class ZipImportTest(unittest.TestCase):
    def setUp(self) -> None:
        import dataclasses
        from unittest import mock

        from services.config import settings

        self.root = Path(tempfile.mkdtemp(prefix="kct-zip-test-"))
        config = dataclasses.replace(settings(), storage_root=self.root / "storage")
        patcher = mock.patch("services.importing.case_import_service.settings", return_value=config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.files = FileService(LocalDisk(self.root / "storage"))
        self.evidences = EvidenceService(self.root / "storage" / "evidences", docx=DocxConverter("python"))
        self.importer = CaseImportService(self.files, self.evidences, docx=DocxConverter("python"))

    def import_zip(self, data: bytes, answers, **kwargs):
        DocumentClassifierAgent.fake(list(answers))
        try:
            return self.importer.import_zip(data, "OneDrive_1_2026-11-07.zip", **kwargs)
        finally:
            DocumentClassifierAgent.stop_faking()

    def test_structured_zip_keeps_source_and_sorts_by_folders(self) -> None:
        result = self.import_zip(ControlFolderFactory(excel_rows=5, pdf_pages=2).zip(), [CD, TP])
        self.assertEqual(result.case_name, ControlFolderFactory.name)                 # from the wrapped folder
        target = self.root / "storage" / "imports" / result.case_id
        self.assertEqual(Path(result.sorted_folder), target)
        self.assertTrue(Path(result.source_zip).is_file())
        self.assertTrue(Path(result.source_zip).name.endswith("_OneDrive_1_2026-11-07.zip"))
        self.assertTrue((target / "Input" / "Evidence" / "Q1 2026" / "EV-03_ADX_audit_log_extract_SAMPLE.xlsx").is_file())
        self.assertTrue((target / "Input" / "Test Plan and Control Details" / TEST_PLAN).is_file())
        self.assertTrue((target / "import.json").is_file())
        self.assertEqual(result.sorted_by_ai, [])                                     # folders decided
        self.assertEqual(len(result.evidence), 4)

    def test_flat_zip_is_sorted_file_by_file(self) -> None:
        # sorted file order: CD (.docx), EV-01, EV-03, EV-04, EV-05, TP (.pdf), notes (.pptx, not readable)
        names = sorted([
            CONTROL_DETAILS, "EV-01_password_reset_tickets_SAMPLE.docx", "EV-03_ADX_audit_log_extract_SAMPLE.xlsx",
            "EV-04_evidence_email_SAMPLE.msg", "EV-05_service_desk_log_export_SAMPLE.pdf", TEST_PLAN])
        roles = {CONTROL_DETAILS: CD, TEST_PLAN: TP}
        evidence = '{"role": "evidence", "reason": "a log"}'
        answers = [roles.get(n, evidence) for n in names]
        result = self.import_zip(ControlFolderFactory(excel_rows=5, pdf_pages=2).zip(flat=True), answers,
                                 case_name="Flat upload")
        self.assertEqual(result.case_id, "Flat-upload")
        by_role = {c.name: c.role for c in result.sorted_by_ai}
        self.assertEqual(by_role[CONTROL_DETAILS], "control_details")
        self.assertEqual(by_role[TEST_PLAN], "test_plan")
        self.assertEqual(by_role["meeting notes.pptx"], "other")
        self.assertEqual(len(result.evidence), 4)
        self.assertTrue((Path(result.sorted_folder) / "other" / "meeting notes.pptx").is_file())

    def test_unsafe_zips_are_refused(self) -> None:
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../../escape.txt", "x")
        with self.assertRaises(ImportFolderError):
            self.importer.import_zip(buffer.getvalue(), "evil.zip")
        with self.assertRaises(ImportFolderError):
            self.importer.import_zip(b"not a zip", "x.zip")


if __name__ == "__main__":
    unittest.main()
