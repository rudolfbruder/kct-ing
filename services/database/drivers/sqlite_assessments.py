"""Assessment tables for the SQLite driver. Lists and nested data are JSON text."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from services.assessment.data import Assessment, AssessedPart, AssessmentMetadata, StepVerdict
from services.database.exceptions import RecordNotFoundError

ASSESSMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id                      TEXT PRIMARY KEY,
    case_id                 TEXT NOT NULL,
    case_reference          TEXT NOT NULL,
    case_interpretation_id  TEXT NOT NULL,
    status                  TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    provider                TEXT NOT NULL,
    model                   TEXT NOT NULL,
    parts_total             INTEGER NOT NULL DEFAULT 0,
    parts_done              INTEGER NOT NULL DEFAULT 0,
    parts_failed            INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL,
    finished_at             TEXT,
    error                   TEXT,
    report_path             TEXT,
    report_sha256           TEXT
);

CREATE TABLE IF NOT EXISTS assessment_parts (
    id             TEXT PRIMARY KEY,
    assessment_id  TEXT NOT NULL REFERENCES assessments (id),
    position       INTEGER NOT NULL,
    unit           TEXT NOT NULL,
    label          TEXT NOT NULL,
    status         TEXT NOT NULL,
    data           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS step_verdicts (
    id              TEXT PRIMARY KEY,
    assessment_id   TEXT NOT NULL REFERENCES assessments (id),
    test_step_id    TEXT NOT NULL,
    step_reference  TEXT NOT NULL,
    verdict         TEXT NOT NULL CHECK (verdict IN ('effective', 'not_effective')),
    no_evidence     INTEGER NOT NULL,
    data            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS assessments_case_reference ON assessments (case_reference);
CREATE INDEX IF NOT EXISTS assessment_parts_assessment_id ON assessment_parts (assessment_id);
CREATE INDEX IF NOT EXISTS step_verdicts_assessment_id ON step_verdicts (assessment_id);
"""

COLUMNS = list(AssessmentMetadata.model_fields)


class SqliteAssessments:
    """Mixed into SqliteRepository, which provides _connect()."""

    def _create_assessment_tables(self, con) -> None:
        con.executescript(ASSESSMENT_SCHEMA)

    def create_assessment(self, metadata: AssessmentMetadata) -> None:
        values = metadata.model_dump()
        values["id"] = values.pop("assessment_id")
        columns = ", ".join(values)
        with self._connect() as con:
            con.execute(f"INSERT INTO assessments ({columns}) VALUES ({', '.join('?' * len(values))})",
                        list(values.values()))

    def update_assessment(self, assessment_id: str, **fields) -> None:
        unknown = set(fields) - set(COLUMNS)
        if unknown:
            raise ValueError(f"Unknown assessment fields {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._connect() as con:
            cursor = con.execute(f"UPDATE assessments SET {assignments} WHERE id = ?",
                                 [*fields.values(), assessment_id])
            if cursor.rowcount == 0:
                raise RecordNotFoundError(f"No assessment {assessment_id}")

    def save_part(self, assessment_id: str, part: AssessedPart) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO assessment_parts (id, assessment_id, position, unit, label, status, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (part.id, assessment_id, part.position, part.unit, part.label, part.status, part.model_dump_json()),
            )

    def save_verdicts(self, assessment_id: str, verdicts: List[StepVerdict]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self._connect() as con:
            con.executemany(
                "INSERT INTO step_verdicts (id, assessment_id, test_step_id, step_reference, verdict, "
                "no_evidence, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(v.id, assessment_id, v.test_step_id, v.step_reference, v.verdict, int(v.no_evidence),
                  v.model_dump_json()) for v in verdicts],
            )
            con.executemany(
                "UPDATE test_steps SET status = ?, updated_at = ? WHERE id = ?",
                [(v.verdict, now, v.test_step_id) for v in verdicts],
            )

    def find_assessment(self, assessment_id: str) -> Assessment:
        with self._connect() as con:
            row = con.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
            if row is None:
                raise RecordNotFoundError(f"No assessment {assessment_id}")
            parts = con.execute("SELECT data FROM assessment_parts WHERE assessment_id = ? ORDER BY position",
                                (assessment_id,)).fetchall()
            verdicts = con.execute("SELECT data FROM step_verdicts WHERE assessment_id = ? ORDER BY rowid",
                                   (assessment_id,)).fetchall()
        return Assessment(
            metadata=_metadata(row),
            parts=[AssessedPart.model_validate_json(p["data"]) for p in parts],
            verdicts=[StepVerdict.model_validate_json(v["data"]) for v in verdicts],
        )

    def assessments(self, case_reference: Optional[str] = None) -> List[AssessmentMetadata]:
        query, params = "SELECT * FROM assessments", ()
        if case_reference is not None:
            query, params = query + " WHERE case_reference = ?", (case_reference,)
        with self._connect() as con:
            rows = con.execute(query + " ORDER BY created_at DESC, rowid DESC", params).fetchall()
        return [_metadata(r) for r in rows]


def _metadata(row) -> AssessmentMetadata:
    values = {name: row["id" if name == "assessment_id" else name] for name in COLUMNS}
    return AssessmentMetadata(**values)
