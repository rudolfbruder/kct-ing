"""SQLite driver: one file, no server, Python's built-in sqlite3 module.

Tables:

    cases                  one row per uploaded case (reference = case-001)
    case_interpretations   one row per Stage 2 run over a case
    test_steps             the steps of one interpretation

IDs are UUIDs, as on BigQuery, so data looks the same on every driver.
Criteria lists are stored as JSON text. The schema is created on first use;
there are no migrations yet, so after a schema change delete the file.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from services.control_testing.data import (
    CaseInterpretation,
    CaseInterpretationMetadata,
    DocumentKind,
    TestStep,
    TestStepDraft,
)
from services.database.exceptions import RecordNotFoundError

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id          TEXT PRIMARY KEY,
    reference   TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_interpretations (
    id                       TEXT PRIMARY KEY,
    case_id                  TEXT NOT NULL REFERENCES cases (id),
    provider                 TEXT NOT NULL,
    model                    TEXT NOT NULL,
    control_details_summary  TEXT NOT NULL,
    test_plan_summary        TEXT NOT NULL,
    created_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_steps (
    id                      TEXT PRIMARY KEY,
    case_interpretation_id  TEXT NOT NULL REFERENCES case_interpretations (id),
    case_id                 TEXT NOT NULL REFERENCES cases (id),
    position                INTEGER NOT NULL,
    reference               TEXT NOT NULL,
    title                   TEXT NOT NULL,
    description             TEXT NOT NULL,
    acceptance_criteria     TEXT NOT NULL,
    refusal_criteria        TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'effective', 'not_effective')),
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS case_interpretations_case_id ON case_interpretations (case_id);
CREATE INDEX IF NOT EXISTS test_steps_case_interpretation_id ON test_steps (case_interpretation_id);
CREATE INDEX IF NOT EXISTS test_steps_case_id ON test_steps (case_id);
"""

METADATA_SELECT = """
SELECT ci.id AS case_interpretation_id, ci.case_id, c.reference AS case_reference,
       ci.provider, ci.model, ci.created_at,
       (SELECT COUNT(*) FROM test_steps ts WHERE ts.case_interpretation_id = ci.id) AS step_count,
       ci.control_details_summary, ci.test_plan_summary
FROM case_interpretations ci
JOIN cases c ON c.id = ci.case_id
"""


class SqliteRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(SCHEMA)

    def create_interpretation(
        self,
        case_reference: str,
        provider: str,
        model: str,
        summaries: Dict[str, str],
        steps: List[TestStepDraft],
    ) -> CaseInterpretation:
        now = _now()
        interpretation_id = _uuid()
        with self._connect() as con:
            case_id = self._case_id(con, case_reference, now)
            con.execute(
                "INSERT INTO case_interpretations "
                "(id, case_id, provider, model, control_details_summary, test_plan_summary, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    interpretation_id,
                    case_id,
                    provider,
                    model,
                    summaries[DocumentKind.CONTROL_DETAILS.value],
                    summaries[DocumentKind.TEST_PLAN.value],
                    now,
                ),
            )
            con.executemany(
                "INSERT INTO test_steps (id, case_interpretation_id, case_id, position, reference, title, "
                "description, acceptance_criteria, refusal_criteria, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        _uuid(),
                        interpretation_id,
                        case_id,
                        position,
                        step.reference,
                        step.title,
                        step.description,
                        json.dumps(step.acceptance_criteria, ensure_ascii=False),
                        json.dumps(step.refusal_criteria, ensure_ascii=False),
                        now,
                        now,
                    )
                    for position, step in enumerate(steps, start=1)
                ],
            )
        return self.find_interpretation(interpretation_id)

    def find_interpretation(self, case_interpretation_id: str) -> CaseInterpretation:
        with self._connect() as con:
            row = con.execute(
                METADATA_SELECT + " WHERE ci.id = ?", (case_interpretation_id,)
            ).fetchone()
            if row is None:
                raise RecordNotFoundError(f"No case interpretation {case_interpretation_id}")
            steps = con.execute(
                "SELECT * FROM test_steps WHERE case_interpretation_id = ? ORDER BY position",
                (case_interpretation_id,),
            ).fetchall()
        return CaseInterpretation(
            metadata=_metadata(row),
            summaries={
                DocumentKind.CONTROL_DETAILS.value: row["control_details_summary"],
                DocumentKind.TEST_PLAN.value: row["test_plan_summary"],
            },
            test_steps=[_step(s) for s in steps],
        )

    def latest_interpretation(self, case_reference: str) -> CaseInterpretation:
        latest = self.interpretations(case_reference)
        if not latest:
            raise RecordNotFoundError(f"No case interpretation for {case_reference}")
        return self.find_interpretation(latest[0].case_interpretation_id)

    def interpretations(self, case_reference: Optional[str] = None) -> List[CaseInterpretationMetadata]:
        query, params = METADATA_SELECT, ()
        if case_reference is not None:
            query, params = query + " WHERE c.reference = ?", (case_reference,)
        with self._connect() as con:
            rows = con.execute(query + " ORDER BY ci.created_at DESC, ci.rowid DESC", params).fetchall()
        return [_metadata(r) for r in rows]

    @staticmethod
    def _case_id(con: sqlite3.Connection, case_reference: str, now: str) -> str:
        """ID of the case row, created on first use."""
        row = con.execute("SELECT id FROM cases WHERE reference = ?", (case_reference,)).fetchone()
        if row is not None:
            return row["id"]
        case_id = _uuid()
        con.execute(
            "INSERT INTO cases (id, reference, created_at) VALUES (?, ?, ?)", (case_id, case_reference, now)
        )
        return case_id

    def _connect(self) -> "_Connection":
        return _Connection(self.path)


class _Connection:
    """A fresh connection per operation; commits on success, rolls back on error."""

    def __init__(self, path: Path) -> None:
        self.con = sqlite3.connect(path, timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")

    def __enter__(self) -> sqlite3.Connection:
        return self.con.__enter__()

    def __exit__(self, *exc) -> None:
        with closing(self.con):
            self.con.__exit__(*exc)


def _metadata(row: sqlite3.Row) -> CaseInterpretationMetadata:
    return CaseInterpretationMetadata(
        **{k: row[k] for k in CaseInterpretationMetadata.model_fields}
    )


def _step(row: sqlite3.Row) -> TestStep:
    return TestStep(
        id=row["id"],
        case_interpretation_id=row["case_interpretation_id"],
        case_id=row["case_id"],
        reference=row["reference"],
        title=row["title"],
        description=row["description"],
        acceptance_criteria=json.loads(row["acceptance_criteria"]),
        refusal_criteria=json.loads(row["refusal_criteria"]),
        status=row["status"],
    )


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
