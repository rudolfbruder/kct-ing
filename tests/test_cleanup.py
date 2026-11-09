"""CleanupService on a temporary storage folder."""
from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from factories import DocxFactory, MsgFactory
from services.config import settings
from services.evidences.docx_converter import DocxConverter
from services.evidences.evidence_service import EvidenceService
from services.maintenance.cleanup_service import CleanupService


class CleanupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = Path(tempfile.mkdtemp(prefix="kct-clean-"))
        self.evidences = self.storage / "evidences"
        config = dataclasses.replace(
            settings(), storage_root=self.storage, evidences_root=self.evidences,
            db_path=self.storage / "database.sqlite", db_driver="sqlite", files_driver="local",
        )
        self.cleanup = CleanupService(config)
        (self.storage / "database.sqlite").write_bytes(b"db")
        (self.storage / "uploads" / "case-001").mkdir(parents=True)
        (self.storage / "logs").mkdir()
        (self.storage / "logs" / "app.log").write_text("x")
        service = EvidenceService(self.evidences, docx=DocxConverter("python"))
        MsgFactory(history=1).create(self.evidences)
        DocxFactory().create(self.evidences)
        self.real = self.evidences / "real_evidence.pdf"
        self.real.write_bytes(b"%PDF-1.4 real")
        service.convert_all()

    def test_plan_deletes_nothing(self) -> None:
        plan = self.cleanup.plan(["database", "evidence_outputs"])
        self.assertTrue(plan)
        self.assertTrue(all(t.path.exists() for t in plan))

    def test_outputs_and_samples_go_real_evidence_stays(self) -> None:
        self.cleanup.run(self.cleanup.plan(["evidence_outputs", "evidence_samples"]))
        self.assertEqual(sorted(p.name for p in self.evidences.iterdir()), ["real_evidence.pdf"])

    def test_outputs_only_keeps_the_originals(self) -> None:
        self.cleanup.run(self.cleanup.plan(["evidence_outputs"]))
        names = sorted(p.name for p in self.evidences.iterdir())
        self.assertEqual(names, [DocxFactory.name, MsgFactory.name, "real_evidence.pdf"])

    def test_database_and_cases_but_not_logs(self) -> None:
        self.cleanup.run(self.cleanup.plan(["database", "cases"]))
        self.assertFalse((self.storage / "database.sqlite").exists())
        self.assertFalse((self.storage / "uploads").exists())
        self.assertTrue((self.storage / "logs" / "app.log").exists())

    def test_cloud_storage_is_never_touched(self) -> None:
        config = dataclasses.replace(self.cleanup.config, db_driver="bigquery", files_driver="gcs",
                                     gcs_bucket="bucket", bq_dataset="dataset")
        plan = CleanupService(config).plan(["database", "cases"])
        self.assertTrue(plan and all(t.skipped for t in plan))
        self.assertEqual(CleanupService(config).run(plan), [])

    def test_refuses_paths_outside_storage(self) -> None:
        from services.maintenance.cleanup_service import Target

        outside = Path(tempfile.mkdtemp(prefix="kct-outside-"))
        with self.assertRaises(RuntimeError):
            self.cleanup.run([Target("logs", outside, 0)])
        self.assertTrue(outside.exists())


if __name__ == "__main__":
    unittest.main()
