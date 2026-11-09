"""Assessment tables for the BigQuery driver. Nested data is JSON text in STRING columns.

Rows are written with DML (never streaming inserts), so they can be updated right away:
the assessment's progress and status change while it runs.
"""
from __future__ import annotations

import json
from typing import List, Optional

from google.cloud import bigquery

from services.assessment.data import Assessment, AssessedPart, AssessmentMetadata, StepVerdict
from services.database.exceptions import RecordNotFoundError

ASSESSMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS `{ds}.assessments` (
    id                      STRING NOT NULL,
    case_id                 STRING NOT NULL,
    case_reference          STRING NOT NULL,
    case_interpretation_id  STRING NOT NULL,
    status                  STRING NOT NULL,
    provider                STRING NOT NULL,
    model                   STRING NOT NULL,
    parts_total             INT64 NOT NULL,
    parts_done              INT64 NOT NULL,
    parts_failed            INT64 NOT NULL,
    created_at              STRING NOT NULL,
    finished_at             STRING,
    error                   STRING,
    report_path             STRING,
    report_sha256           STRING
)
CLUSTER BY case_reference;

CREATE TABLE IF NOT EXISTS `{ds}.assessment_parts` (
    id             STRING NOT NULL,
    assessment_id  STRING NOT NULL,
    position       INT64 NOT NULL,
    unit           STRING NOT NULL,
    label          STRING NOT NULL,
    status         STRING NOT NULL,
    data           STRING NOT NULL
)
CLUSTER BY assessment_id;

CREATE TABLE IF NOT EXISTS `{ds}.step_verdicts` (
    id              STRING NOT NULL,
    assessment_id   STRING NOT NULL,
    test_step_id    STRING NOT NULL,
    step_reference  STRING NOT NULL,
    verdict         STRING NOT NULL,
    no_evidence     BOOL NOT NULL,
    data            STRING NOT NULL
)
CLUSTER BY assessment_id;
"""

TYPES = {"parts_total": "INT64", "parts_done": "INT64", "parts_failed": "INT64"}
COLUMNS = list(AssessmentMetadata.model_fields)


def _param(name: str, value, type_: str = "STRING") -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, type_, value)


class BigQueryAssessments:
    """Mixed into BigQueryRepository, which provides _query()."""

    def create_assessment(self, metadata: AssessmentMetadata) -> None:
        values = metadata.model_dump()
        values["id"] = values.pop("assessment_id")
        self._query(
            f"INSERT INTO `{{ds}}.assessments` ({', '.join(values)}) VALUES ({', '.join('@' + k for k in values)})",
            *[_param(k, v, TYPES.get(k, "STRING")) for k, v in values.items()],
        )

    def update_assessment(self, assessment_id: str, **fields) -> None:
        unknown = set(fields) - set(COLUMNS)
        if unknown:
            raise ValueError(f"Unknown assessment fields {sorted(unknown)}")
        if not fields:
            return
        self._query(
            f"UPDATE `{{ds}}.assessments` SET {', '.join(f'{k} = @{k}' for k in fields)} WHERE id = @id",
            _param("id", assessment_id), *[_param(k, v, TYPES.get(k, "STRING")) for k, v in fields.items()],
        )

    def save_part(self, assessment_id: str, part: AssessedPart) -> None:
        self._query(
            "INSERT INTO `{ds}.assessment_parts` (id, assessment_id, position, unit, label, status, data) "
            "VALUES (@id, @assessment_id, @position, @unit, @label, @status, @data)",
            _param("id", part.id), _param("assessment_id", assessment_id), _param("position", part.position, "INT64"),
            _param("unit", part.unit), _param("label", part.label), _param("status", part.status),
            _param("data", part.model_dump_json()),
        )

    def save_verdicts(self, assessment_id: str, verdicts: List[StepVerdict]) -> None:
        rows = json.dumps([{"id": v.id, "test_step_id": v.test_step_id, "step_reference": v.step_reference,
                            "verdict": v.verdict, "no_evidence": v.no_evidence, "data": v.model_dump_json()}
                           for v in verdicts])
        self._query(
            """
BEGIN TRANSACTION;
INSERT INTO `{ds}.step_verdicts` (id, assessment_id, test_step_id, step_reference, verdict, no_evidence, data)
SELECT JSON_VALUE(v, '$.id'), @assessment_id, JSON_VALUE(v, '$.test_step_id'), JSON_VALUE(v, '$.step_reference'),
       JSON_VALUE(v, '$.verdict'), BOOL(JSON_QUERY(v, '$.no_evidence')), JSON_VALUE(v, '$.data')
FROM UNNEST(JSON_QUERY_ARRAY(@rows)) AS v;
UPDATE `{ds}.test_steps` t
SET status = JSON_VALUE(v, '$.verdict'), updated_at = CURRENT_TIMESTAMP()
FROM UNNEST(JSON_QUERY_ARRAY(@rows)) AS v
WHERE t.id = JSON_VALUE(v, '$.test_step_id');
COMMIT TRANSACTION;
""",
            _param("assessment_id", assessment_id), _param("rows", rows),
        )

    def find_assessment(self, assessment_id: str) -> Assessment:
        rows = self._query("SELECT * FROM `{ds}.assessments` WHERE id = @id", _param("id", assessment_id))
        if not rows:
            raise RecordNotFoundError(f"No assessment {assessment_id}")
        parts = self._query("SELECT data FROM `{ds}.assessment_parts` WHERE assessment_id = @id ORDER BY position",
                            _param("id", assessment_id))
        verdicts = self._query("SELECT data FROM `{ds}.step_verdicts` WHERE assessment_id = @id",
                               _param("id", assessment_id))
        return Assessment(
            metadata=_metadata(rows[0]),
            parts=[AssessedPart.model_validate_json(p["data"]) for p in parts],
            verdicts=[StepVerdict.model_validate_json(v["data"]) for v in verdicts],
        )

    def assessments(self, case_reference: Optional[str] = None) -> List[AssessmentMetadata]:
        if case_reference is None:
            rows = self._query("SELECT * FROM `{ds}.assessments` ORDER BY created_at DESC")
        else:
            rows = self._query("SELECT * FROM `{ds}.assessments` WHERE case_reference = @case ORDER BY created_at DESC",
                               _param("case", case_reference))
        return [_metadata(r) for r in rows]


def _metadata(row) -> AssessmentMetadata:
    return AssessmentMetadata(**{name: row["id" if name == "assessment_id" else name] for name in COLUMNS})
