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


if __name__ == "__main__":
    unittest.main()
