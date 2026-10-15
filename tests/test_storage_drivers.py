"""File disks and the BigQuery driver, with the Google Cloud calls replaced."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from google.api_core.exceptions import NotFound, PreconditionFailed

from services.control_testing.data import DocumentKind, TestStepDraft
from services.database.exceptions import DatabaseConfigurationError, RecordNotFoundError
from services.files.disks.local import LocalDisk
from services.files.exceptions import CaseNotFoundError
from services.files.file_service import FileService, UploadedFile

PDF = b"%PDF-1.4\n%%EOF\n"


def uploads():
    return {
        DocumentKind.CONTROL_DETAILS: [UploadedFile("../cd.pdf", PDF)],
        DocumentKind.TEST_PLAN: [UploadedFile("tp", PDF)],
    }


class FileServiceOnLocalDiskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="kct-files-"))
        self.files = FileService(LocalDisk(self.root))

    def test_store_and_read_a_case(self) -> None:
        self.assertEqual(self.files.store_case(uploads()), "case-001")
        self.assertEqual(self.files.store_case(uploads()), "case-002")
        self.assertEqual(self.files.case_ids(), ["case-001", "case-002"])
        self.assertEqual(self.files.document_names("case-001", DocumentKind.TEST_PLAN), ["tp.pdf"])
        [doc] = self.files.documents("case-001", DocumentKind.CONTROL_DETAILS)
        self.assertEqual((doc.data, doc.title), (PDF, "Control details: cd.pdf"))
        self.assertTrue((self.root / "uploads/case-001/control_details/cd.pdf").is_file())

        self.files.save_output("case-001", "x.md", "hello")
        self.assertEqual((self.root / "outputs/case-001/x.md").read_text(), "hello")

    def test_skips_a_taken_case_number(self) -> None:
        disk = self.files.disk
        self.files.store_case(uploads())
        real_directories = disk.directories
        # Simulate a concurrent upload that claimed case-002 after we listed the cases.
        disk.put("uploads/case-002/.case", b"", only_if_missing=True)
        with mock.patch.object(disk, "directories", lambda d: real_directories(d)[:1]):
            self.assertEqual(self.files.store_case(uploads()), "case-003")

    def test_unknown_case(self) -> None:
        with self.assertRaises(CaseNotFoundError):
            self.files.documents("case-404", DocumentKind.TEST_PLAN)


class GcsDiskTest(unittest.TestCase):
    def setUp(self) -> None:
        from services.files.disks.gcs import GcsDisk

        with mock.patch("google.cloud.storage.Client") as client:
            self.disk = GcsDisk("kct-bucket", prefix="kct/", project="p")
        self.client = client.return_value
        self.bucket = self.client.bucket.return_value

    def test_put_and_get_use_the_prefix(self) -> None:
        self.assertTrue(self.disk.put("uploads/case-001/.case", b"", only_if_missing=True))
        self.bucket.blob.assert_called_with("kct/uploads/case-001/.case")
        self.bucket.blob.return_value.upload_from_string.assert_called_with(b"", if_generation_match=0)

        self.bucket.blob.return_value.download_as_bytes.return_value = PDF
        self.assertEqual(self.disk.get("uploads/case-001/test_plan/tp.pdf"), PDF)

    def test_put_only_if_missing_returns_false_when_taken(self) -> None:
        self.bucket.blob.return_value.upload_from_string.side_effect = PreconditionFailed("taken")
        self.assertFalse(self.disk.put("uploads/case-001/.case", b"", only_if_missing=True))

    def test_get_missing_raises_file_not_found(self) -> None:
        self.bucket.blob.return_value.download_as_bytes.side_effect = NotFound("gone")
        with self.assertRaises(FileNotFoundError):
            self.disk.get("nope")

    def test_listing(self) -> None:
        listing = mock.MagicMock()
        blobs = [mock.Mock(), mock.Mock()]
        blobs[0].name, blobs[1].name = "kct/uploads/case-001/test_plan/b.pdf", "kct/uploads/case-001/test_plan/a.pdf"
        listing.__iter__.return_value = iter(blobs)
        listing.prefixes = {"kct/uploads/case-002/", "kct/uploads/case-001/"}
        self.client.list_blobs.return_value = listing

        self.assertEqual(self.disk.files("uploads/case-001/test_plan"), ["a.pdf", "b.pdf"])
        self.client.list_blobs.assert_called_with(
            self.bucket, prefix="kct/uploads/case-001/test_plan/", delimiter="/"
        )
        self.assertEqual(self.disk.directories("uploads"), ["case-001", "case-002"])


class BigQueryRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        from services.database.drivers.bigquery import BigQueryRepository

        with mock.patch("google.cloud.bigquery.Client") as client:
            client.return_value.project = "p"
            self.db = BigQueryRepository("kct", project="p", location="EU")
        self.client = client.return_value
        client.assert_called_with(project="p", location="EU")

    def sql(self, call) -> str:
        return call.args[0]

    def params(self, call) -> dict:
        return {p.name: p.value for p in call.kwargs["job_config"].query_parameters}

    def test_creates_tables_in_the_dataset(self) -> None:
        ddl = self.sql(self.client.query.call_args_list[0])
        for table in ["cases", "case_interpretations", "test_steps"]:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS `p.kct.{table}`", ddl)

    def test_missing_dataset_is_a_configuration_error(self) -> None:
        from services.database.drivers.bigquery import BigQueryRepository

        with mock.patch("google.cloud.bigquery.Client") as client:
            client.return_value.query.side_effect = NotFound("dataset")
            with self.assertRaises(DatabaseConfigurationError):
                BigQueryRepository("other.kct")
        with self.assertRaises(DatabaseConfigurationError):
            BigQueryRepository("")

    def test_create_interpretation_runs_one_transaction(self) -> None:
        now = datetime(2026, 10, 15, tzinfo=timezone.utc)
        meta_row = {
            "case_interpretation_id": "i-1", "case_id": "c-1", "case_reference": "case-001",
            "provider": "gemini", "model": "gemini-2.5-pro", "created_at": now, "step_count": 1,
            "control_details_summary": "# CD", "test_plan_summary": "# TP",
        }
        step_row = {
            "id": "s-1", "case_interpretation_id": "i-1", "case_id": "c-1", "position": 1,
            "reference": "0472-01", "title": "T", "description": "D",
            "acceptance_criteria": ["ok"], "refusal_criteria": ["not ok"], "status": "pending",
        }
        results = iter([[], [meta_row], [step_row]])
        self.client.query.reset_mock()
        self.client.query.side_effect = lambda *a, **k: mock.Mock(result=lambda: next(results))

        created = self.db.create_interpretation(
            "case-001", "gemini", "gemini-2.5-pro",
            {"control_details": "# CD", "test_plan": "# TP"},
            [TestStepDraft(reference="0472-01", title="T", description="D",
                           acceptance_criteria=["ok"], refusal_criteria=["not ok"])],
        )

        insert = self.client.query.call_args_list[0]
        self.assertTrue(self.sql(insert).strip().startswith("BEGIN TRANSACTION;"))
        self.assertIn("INSERT INTO `p.kct.test_steps`", self.sql(insert))
        params = self.params(insert)
        self.assertEqual(params["reference"], "case-001")
        self.assertIn('"reference": "0472-01"', params["steps"])
        self.assertEqual(self.params(self.client.query.call_args_list[1])["id"], params["interpretation_id"])

        self.assertEqual(created.metadata.created_at, "2026-10-15T00:00:00+00:00")
        self.assertEqual(created.test_steps[0].acceptance_criteria, ["ok"])
        self.assertEqual(created.summaries["test_plan"], "# TP")

    def test_unknown_interpretation(self) -> None:
        self.client.query.return_value.result.return_value = []
        with self.assertRaises(RecordNotFoundError):
            self.db.find_interpretation("nope")
        with self.assertRaises(RecordNotFoundError):
            self.db.latest_interpretation("case-404")


if __name__ == "__main__":
    unittest.main()
