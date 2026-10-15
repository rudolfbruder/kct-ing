"""BigQuery driver.

Same three tables as the SQLite driver, in the dataset KCT_BQ_DATASET:

    cases                  one row per uploaded case (reference = case-001)
    case_interpretations   one row per Stage 2 run over a case
    test_steps             the steps of one interpretation

BigQuery has no auto-increment, so IDs are UUIDs made in Python. Rows are
written with DML INSERT inside one transaction, never with streaming inserts:
streamed rows cannot be updated for up to 90 minutes, and Stage 3 updates
each step's status. Tables are created on first use; the dataset must exist.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from services.control_testing.data import (
    CaseInterpretation,
    CaseInterpretationMetadata,
    DocumentKind,
    TestStep,
    TestStepDraft,
)
from services.database.exceptions import DatabaseConfigurationError, RecordNotFoundError

SCHEMA = """
CREATE TABLE IF NOT EXISTS `{ds}.cases` (
    id          STRING NOT NULL,
    reference   STRING NOT NULL,
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `{ds}.case_interpretations` (
    id                       STRING NOT NULL,
    case_id                  STRING NOT NULL,
    provider                 STRING NOT NULL,
    model                    STRING NOT NULL,
    control_details_summary  STRING NOT NULL,
    test_plan_summary        STRING NOT NULL,
    created_at               TIMESTAMP NOT NULL
)
CLUSTER BY case_id;

CREATE TABLE IF NOT EXISTS `{ds}.test_steps` (
    id                      STRING NOT NULL,
    case_interpretation_id  STRING NOT NULL,
    case_id                 STRING NOT NULL,
    position                INT64 NOT NULL,
    reference               STRING NOT NULL,
    title                   STRING NOT NULL,
    description             STRING NOT NULL,
    acceptance_criteria     ARRAY<STRING>,
    refusal_criteria        ARRAY<STRING>,
    status                  STRING NOT NULL,
    created_at              TIMESTAMP NOT NULL,
    updated_at              TIMESTAMP NOT NULL
)
CLUSTER BY case_interpretation_id;
"""

# One transaction: the case row (first time only), the interpretation, its steps.
# Steps arrive as one JSON parameter and are unpacked with UNNEST.
CREATE_INTERPRETATION = """
BEGIN TRANSACTION;

INSERT INTO `{ds}.cases` (id, reference, created_at)
SELECT @new_case_id, @reference, @now
FROM UNNEST([1])
WHERE NOT EXISTS (SELECT 1 FROM `{ds}.cases` WHERE reference = @reference);

INSERT INTO `{ds}.case_interpretations`
    (id, case_id, provider, model, control_details_summary, test_plan_summary, created_at)
SELECT @interpretation_id, c.id, @provider, @model, @control_details_summary, @test_plan_summary, @now
FROM `{ds}.cases` c
WHERE c.reference = @reference;

INSERT INTO `{ds}.test_steps`
    (id, case_interpretation_id, case_id, position, reference, title, description,
     acceptance_criteria, refusal_criteria, status, created_at, updated_at)
SELECT JSON_VALUE(s, '$.id'), @interpretation_id, c.id, pos + 1,
       JSON_VALUE(s, '$.reference'), JSON_VALUE(s, '$.title'), JSON_VALUE(s, '$.description'),
       JSON_VALUE_ARRAY(s, '$.acceptance_criteria'), JSON_VALUE_ARRAY(s, '$.refusal_criteria'),
       'pending', @now, @now
FROM `{ds}.cases` c, UNNEST(JSON_QUERY_ARRAY(@steps)) AS s WITH OFFSET AS pos
WHERE c.reference = @reference;

COMMIT TRANSACTION;
"""

METADATA_SELECT = """
SELECT ci.id AS case_interpretation_id, ci.case_id, c.reference AS case_reference,
       ci.provider, ci.model, ci.created_at,
       (SELECT COUNT(*) FROM `{ds}.test_steps` ts WHERE ts.case_interpretation_id = ci.id) AS step_count,
       ci.control_details_summary, ci.test_plan_summary
FROM `{ds}.case_interpretations` ci
JOIN `{ds}.cases` c ON c.id = ci.case_id
"""


class BigQueryRepository:
    def __init__(self, dataset: str, project: str = "", location: str = "") -> None:
        if not dataset:
            raise DatabaseConfigurationError("KCT_DB_DRIVER=bigquery needs KCT_BQ_DATASET")
        self.client = bigquery.Client(project=project or None, location=location or None)
        # "dataset" means a dataset in the client's project; "project.dataset" is used as is.
        self.dataset = dataset if "." in dataset else f"{self.client.project}.{dataset}"
        try:
            self._query(SCHEMA)
        except NotFound as exc:
            raise DatabaseConfigurationError(
                f"BigQuery dataset {self.dataset} not found. Create it first, in the same "
                f"location as KCT_BQ_LOCATION."
            ) from exc

    def create_interpretation(
        self,
        case_reference: str,
        provider: str,
        model: str,
        summaries: Dict[str, str],
        steps: List[TestStepDraft],
    ) -> CaseInterpretation:
        interpretation_id = _uuid()
        steps_json = json.dumps(
            [{"id": _uuid(), **step.model_dump()} for step in steps], ensure_ascii=False
        )
        self._query(
            CREATE_INTERPRETATION,
            _param("new_case_id", _uuid()),
            _param("reference", case_reference),
            _param("now", datetime.now(timezone.utc), "TIMESTAMP"),
            _param("interpretation_id", interpretation_id),
            _param("provider", provider),
            _param("model", model),
            _param("control_details_summary", summaries[DocumentKind.CONTROL_DETAILS.value]),
            _param("test_plan_summary", summaries[DocumentKind.TEST_PLAN.value]),
            _param("steps", steps_json),
        )
        return self.find_interpretation(interpretation_id)

    def find_interpretation(self, case_interpretation_id: str) -> CaseInterpretation:
        rows = self._query(METADATA_SELECT + " WHERE ci.id = @id", _param("id", case_interpretation_id))
        if not rows:
            raise RecordNotFoundError(f"No case interpretation {case_interpretation_id}")
        row = rows[0]
        steps = self._query(
            "SELECT * FROM `{ds}.test_steps` WHERE case_interpretation_id = @id ORDER BY position",
            _param("id", case_interpretation_id),
        )
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
        if case_reference is None:
            rows = self._query(METADATA_SELECT + " ORDER BY ci.created_at DESC")
        else:
            rows = self._query(
                METADATA_SELECT + " WHERE c.reference = @reference ORDER BY ci.created_at DESC",
                _param("reference", case_reference),
            )
        return [_metadata(r) for r in rows]

    def _query(self, sql: str, *params: bigquery.ScalarQueryParameter) -> list:
        job = self.client.query(
            sql.replace("{ds}", self.dataset),
            job_config=bigquery.QueryJobConfig(query_parameters=list(params)),
        )
        return list(job.result())


def _param(name: str, value, type_: str = "STRING") -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, type_, value)


def _metadata(row) -> CaseInterpretationMetadata:
    values = {k: row[k] for k in CaseInterpretationMetadata.model_fields}
    values["created_at"] = _timestamp(values["created_at"])
    return CaseInterpretationMetadata(**values)


def _step(row) -> TestStep:
    return TestStep(
        id=row["id"],
        case_interpretation_id=row["case_interpretation_id"],
        case_id=row["case_id"],
        reference=row["reference"],
        title=row["title"],
        description=row["description"],
        acceptance_criteria=list(row["acceptance_criteria"] or []),
        refusal_criteria=list(row["refusal_criteria"] or []),
        status=row["status"],
    )


def _timestamp(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _uuid() -> str:
    return str(uuid.uuid4())
