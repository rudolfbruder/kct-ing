"""SQLite repository and the notebook script, on a temporary database file."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from scripts.test_steps import render
from services.control_testing.data import TestStepDraft
from services.database.drivers.sqlite import SqliteRepository
from services.database.exceptions import RecordNotFoundError

SUMMARIES = {"control_details": "# CD", "test_plan": "# TP"}


def draft(reference: str) -> TestStepDraft:
    return TestStepDraft(
        reference=reference,
        title=f"Step {reference}",
        description="Inspect the evidence.",
        acceptance_criteria=["It holds."],
        refusal_criteria=["It does not hold."],
    )


class SqliteRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(tempfile.mkdtemp(prefix="kct-db-")) / "test.sqlite"
        self.db = SqliteRepository(self.path)

    def create(self, case_reference: str = "case-001", references=("0472-01", "DERIVED-01")):
        return self.db.create_interpretation(
            case_reference, "fake", "fake", SUMMARIES, [draft(r) for r in references]
        )

    def test_ids_are_uuids_made_by_the_repository(self) -> None:
        first = self.create()
        meta = first.metadata
        for value in [meta.case_interpretation_id, meta.case_id] + [s.id for s in first.test_steps]:
            uuid.UUID(value)
        self.assertEqual([s.reference for s in first.test_steps], ["0472-01", "DERIVED-01"])
        for step in first.test_steps:
            self.assertEqual(step.case_interpretation_id, meta.case_interpretation_id)
            self.assertEqual(step.case_id, meta.case_id)

        second = self.create()
        self.assertNotEqual(second.metadata.case_interpretation_id, meta.case_interpretation_id)
        self.assertEqual(second.metadata.case_id, meta.case_id)  # same case row
        self.assertFalse({s.id for s in first.test_steps} & {s.id for s in second.test_steps})

        self.assertNotEqual(self.create("case-002", ["A"]).metadata.case_id, meta.case_id)

    def test_tables(self) -> None:
        created = self.create()
        with sqlite3.connect(self.path) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            step = con.execute(
                "SELECT case_interpretation_id, case_id, status FROM test_steps ORDER BY position"
            ).fetchone()
        self.assertTrue({"cases", "case_interpretations", "test_steps"} <= tables)
        self.assertEqual(
            step, (created.metadata.case_interpretation_id, created.metadata.case_id, "pending")
        )

    def test_reads(self) -> None:
        first = self.create()
        second = self.create()
        first_id = first.metadata.case_interpretation_id
        second_id = second.metadata.case_interpretation_id
        self.assertEqual(self.db.find_interpretation(first_id), first)
        self.assertEqual(self.db.latest_interpretation("case-001"), second)
        self.assertEqual(
            [m.case_interpretation_id for m in self.db.interpretations("case-001")],
            [second_id, first_id],
        )
        self.assertEqual(self.db.interpretations("case-404"), [])
        with self.assertRaises(RecordNotFoundError):
            self.db.find_interpretation("no-such-id")
        with self.assertRaises(RecordNotFoundError):
            self.db.latest_interpretation("case-404")

    def test_failed_insert_leaves_nothing_behind(self) -> None:
        with self.assertRaises(KeyError):
            self.db.create_interpretation("case-001", "fake", "fake", {}, [draft("A")])
        self.assertEqual(self.db.interpretations(), [])

    def test_script_output_starts_with_metadata(self) -> None:
        created = self.create()
        text = render(created)
        header = text.split("Test step", 1)[0]
        self.assertIn(f"Case interpretation {created.metadata.case_interpretation_id}", header)
        self.assertIn(f"case_id:     {created.metadata.case_id} (case-001)", header)
        self.assertIn(
            f"Test step {created.test_steps[0].id}  [pending]  0472-01: Step 0472-01", text
        )



class MemoryRepositoryTest(unittest.TestCase):
    def test_reads_like_the_other_drivers_and_writes_no_file(self) -> None:
        from services.database.drivers.memory import MemoryRepository

        db = MemoryRepository()
        first = db.create_interpretation("case-001", "fake", "fake", SUMMARIES, [draft("A"), draft("B")])
        second = db.create_interpretation("case-001", "fake", "fake", SUMMARIES, [draft("A")])
        self.assertEqual(first.metadata.step_count, 2)
        self.assertEqual(first.metadata.case_id, second.metadata.case_id)
        self.assertEqual(len(first.test_steps[0].id), 36)
        self.assertEqual(first.test_steps[0].status, "pending")
        self.assertEqual(db.find_interpretation(first.metadata.case_interpretation_id), first)
        self.assertEqual(db.latest_interpretation("case-001"), second)
        self.assertEqual(
            [m.case_interpretation_id for m in db.interpretations()],
            [second.metadata.case_interpretation_id, first.metadata.case_interpretation_id],
        )
        with self.assertRaises(RecordNotFoundError):
            db.latest_interpretation("case-404")



class AssessmentStorageTest(unittest.TestCase):
    """The same assessment round trip on the memory and SQLite drivers."""

    def drivers(self):
        from services.database.drivers.memory import MemoryRepository

        yield MemoryRepository()
        yield SqliteRepository(Path(tempfile.mkdtemp(prefix="kct-db-")) / "test.sqlite")

    def test_round_trip_and_step_status(self) -> None:
        from services.assessment.data import AssessedPart, AssessmentMetadata, CheckedStepFinding, StepVerdict

        for db in self.drivers():
            with self.subTest(driver=type(db).__name__):
                interpretation = db.create_interpretation("case-001", "fake", "fake", SUMMARIES, [draft("A"), draft("B")])
                step_a, step_b = interpretation.test_steps
                meta = AssessmentMetadata(
                    assessment_id=str(uuid.uuid4()), case_id=interpretation.metadata.case_id,
                    case_reference="case-001", case_interpretation_id=interpretation.metadata.case_interpretation_id,
                    status="queued", provider="fake", model="fake", created_at="2026-11-07T00:00:00+00:00")
                db.create_assessment(meta)
                db.update_assessment(meta.assessment_id, status="running", parts_total=1)
                db.save_part(meta.assessment_id, AssessedPart(
                    id="p-1", position=1, unit="EV-01.pdf", unit_sha256="abc", part_number=1, part_total=1,
                    label="EV-01.pdf", documents=["EV-01.pdf"], estimated_tokens=10, status="assessed",
                    findings=[CheckedStepFinding(step_reference="A", relevance="supports", reference_problems=["x"])]))
                db.save_verdicts(meta.assessment_id, [
                    StepVerdict(id="v-1", test_step_id=step_a.id, step_reference="A", title="T", verdict="effective",
                                no_evidence=False, reason="ok"),
                    StepVerdict(id="v-2", test_step_id=step_b.id, step_reference="B", title="T",
                                verdict="not_effective", no_evidence=True, reason="none"),
                ])
                db.update_assessment(meta.assessment_id, status="completed")

                found = db.find_assessment(meta.assessment_id)
                self.assertEqual(found.metadata.status, "completed")
                self.assertEqual(found.metadata.parts_total, 1)
                self.assertEqual(found.parts[0].findings[0].reference_problems, ["x"])
                self.assertEqual([v.verdict for v in found.verdicts], ["effective", "not_effective"])
                self.assertEqual([m.assessment_id for m in db.assessments("case-001")], [meta.assessment_id])
                self.assertEqual(db.assessments("case-404"), [])
                statuses = {s.reference: s.status for s in db.find_interpretation(
                    interpretation.metadata.case_interpretation_id).test_steps}
                self.assertEqual(statuses, {"A": "effective", "B": "not_effective"})
                with self.assertRaises(RecordNotFoundError):
                    db.find_assessment("nope")


if __name__ == "__main__":
    unittest.main()
