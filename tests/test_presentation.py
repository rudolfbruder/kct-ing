"""Traceability matrix, record & replay, run figures, and the notebook building blocks."""
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.ai.attachments import Document
from services.ai.providers.base import ProviderRequest
from services.ai.providers.fake import FakeProvider
from services.ai.providers.replay import RecordingProvider, ReplayProvider
from services.assessment.data import (
    AssessedPart,
    Assessment,
    AssessmentMetadata,
    CheckedStepFinding,
    StepVerdict,
)
from services.assessment.matrix import Matrix, traceability
from services.config import BASE

META = AssessmentMetadata(assessment_id="a", case_id="c", case_reference="case-1", case_interpretation_id="i",
                          status="completed", provider="fake", model="fake", created_at="2026-11-07T00:00:00+00:00")


def part(unit, number, findings, status="assessed"):
    return AssessedPart(id=f"{unit}{number}", position=number, unit=unit, unit_sha256="x", part_number=number,
                        part_total=2, label=unit, documents=[], estimated_tokens=1, status=status,
                        findings=[CheckedStepFinding(step_reference=r, relevance=v) for r, v in findings])


def verdict(reference, value="effective"):
    return StepVerdict(id=reference, test_step_id=reference, step_reference=reference, title=reference,
                       verdict=value, no_evidence=False, reason="")


class MatrixTest(unittest.TestCase):
    def test_strongest_finding_per_file_wins(self) -> None:
        assessment = Assessment(metadata=META, parts=[
            part("logs/EV-05.pdf", 1, [("A", "supports"), ("B", "not_relevant")]),
            part("logs/EV-05.pdf", 2, [("A", "contradicts"), ("B", "partly")]),
            part("EV-01.docx", 1, [("A", "not_relevant")], status="failed"),
        ], verdicts=[verdict("A", "not_effective"), verdict("B")])
        matrix = traceability(assessment)
        self.assertEqual(matrix.units, ["EV-01.docx", "logs/EV-05.pdf"])          # sorted by short name
        self.assertEqual(matrix.cell("A", "logs/EV-05.pdf"), "contradicts")
        self.assertEqual(matrix.cell("B", "logs/EV-05.pdf"), "partly")
        self.assertEqual(matrix.cell("A", "EV-01.docx"), "failed")
        self.assertEqual(Matrix.short("logs/EV-05.pdf"), "EV-05")
        self.assertEqual(Matrix.short("a very long evidence file name.xlsx"), "a very long evid…")


class RecordReplayTest(unittest.TestCase):
    def request(self, prompt="Summarize.", title="CD.pdf"):
        return ProviderRequest(agent="control_details_summary", instructions="i", prompt=prompt,
                               attachments=[Document(data=b"%PDF", title=title)], model="m", max_tokens=1000,
                               temperature=0, output_schema=None)

    def test_recorded_answers_come_back_exactly(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="kct-rec-")) / "demo"
        live = RecordingProvider(FakeProvider(BASE / "tests" / "fixtures" / "fake_ai"), folder)
        original = live.prompt(self.request())
        replayed = ReplayProvider(folder).prompt(self.request())
        self.assertEqual(replayed.text, original.text)
        self.assertEqual(replayed.usage.output_tokens, original.usage.output_tokens)
        self.assertIn("(replay)", replayed.model)
        # same file name, different bytes: still the same answer
        self.assertEqual(ReplayProvider(folder).prompt(self.request()).text, original.text)

    def test_unknown_call_takes_the_next_recording_and_missing_recordings_fail_clearly(self) -> None:
        from services.ai.exceptions import AiConfigurationError

        folder = Path(tempfile.mkdtemp(prefix="kct-rec-")) / "demo"
        RecordingProvider(FakeProvider(BASE / "tests" / "fixtures" / "fake_ai"), folder).prompt(self.request())
        self.assertTrue(ReplayProvider(folder).prompt(self.request(prompt="Something else.")).text)
        with self.assertRaises(AiConfigurationError):
            ReplayProvider(folder.parent / "missing")


class MetricsAndUpgradeTest(unittest.TestCase):
    def test_old_sqlite_database_gets_the_new_columns(self) -> None:
        from services.database.drivers.sqlite import SqliteRepository

        path = Path(tempfile.mkdtemp(prefix="kct-old-")) / "old.sqlite"
        with sqlite3.connect(path) as con:   # an assessments table as the previous version made it
            con.execute("CREATE TABLE assessments (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, case_reference TEXT "
                        "NOT NULL, case_interpretation_id TEXT NOT NULL, status TEXT NOT NULL, provider TEXT NOT NULL, "
                        "model TEXT NOT NULL, parts_total INTEGER NOT NULL DEFAULT 0, parts_done INTEGER NOT NULL "
                        "DEFAULT 0, parts_failed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, finished_at TEXT, "
                        "error TEXT, report_path TEXT, report_sha256 TEXT)")
            con.execute("INSERT INTO assessments (id, case_id, case_reference, case_interpretation_id, status, provider, "
                        "model, created_at) VALUES ('old', 'c', 'case-1', 'i', 'completed', 'fake', 'fake', 't')")
        db = SqliteRepository(path)
        self.assertEqual(db.find_assessment("old").metadata.input_tokens, 0)
        db.update_assessment("old", input_tokens=10, duration_seconds=1.5, estimated_cost=0.01)
        meta = db.find_assessment("old").metadata
        self.assertEqual((meta.input_tokens, meta.duration_seconds, meta.estimated_cost), (10, 1.5, 0.01))


@unittest.skipUnless(importlib.util.find_spec("IPython"), "IPython is not installed (it comes with Jupyter)")
class NotebookBlocksTest(unittest.TestCase):
    def test_blocks_render_and_left_align_cells(self) -> None:
        from services.presentation import notebook as show

        assessment = Assessment(metadata=META, parts=[part("EV-01.docx", 1, [("A", "supports")])],
                                verdicts=[verdict("A")])
        for block in (show.kpis(assessment), show.matrix(assessment), show.trust(assessment),
                      show.savings(assessment, None), show.savings(assessment, 6, 80, "EUR"),
                      show.verdict_card(assessment.verdicts[0])):
            self.assertIn("class='kct'", block.data)
        html = show.matrix(assessment).data
        self.assertIn("✓", html)
        self.assertNotIn("<td>", html)                     # every cell carries its own alignment
        self.assertIn("6 h", show.savings(assessment, 6).data)


if __name__ == "__main__":
    unittest.main()
