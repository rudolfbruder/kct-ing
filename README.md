# KCT

Key Control Testing helper. Takes a process's control details and test plan
(PDF), summarizes them and turns them into test steps, using Gemini or Claude.

| Stage | What it does | Status |
|---|---|---|
| 1 | Summarize control details or test plan into structured Markdown | done |
| 2 | Upload both documents, summarize them and generate test steps (JSON) | done |
| 3 | Upload evidence and judge each test step effective / not effective | not started |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # skip what the workbench already has
cp .env.example .env                 # then fill it in
```

Nothing loads `.env` automatically. Export it into your shell before starting:

```bash
set -a; source .env; set +a
```

Gemini and Claude on Vertex AI use Google Application Default Credentials. On
the Vertex workbench this works out of the box; elsewhere run
`gcloud auth application-default login`.

## Launch

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive docs (try every endpoint from the browser): http://localhost:8000/docs

## Choosing the AI provider

Set `KCT_AI_PROVIDER`; every agent then runs on that provider. Nothing else changes.

| `KCT_AI_PROVIDER` | Runs on | Needs |
|---|---|---|
| `gemini` (default) | Gemini on Vertex AI | `KCT_PROJECT_ID`, `google-genai` |
| `anthropic` | Claude on Vertex AI (`KCT_ANTHROPIC_PLATFORM=vertex`) or the Anthropic API (`api`) | `KCT_PROJECT_ID` or `ANTHROPIC_API_KEY`, `anthropic[vertex]` |
| `fake` | Fixture files in `tests/fixtures/fake_ai/` | nothing |

`KCT_AI_MODEL` picks the model, for example `gemini-2.5-pro`, `claude-opus-5-5`
or `claude-sonnet-5-5`. Which Claude models your project can use depends on
what is enabled in Vertex AI Model Garden; check there, and check the region
(`KCT_ANTHROPIC_REGION`) the model is offered in.

### Fake mode

```bash
KCT_AI_PROVIDER=fake KCT_STORAGE_ROOT=/tmp/kct uvicorn main:app --port 8000 --reload
```

Each agent answers with `tests/fixtures/fake_ai/<agent name>.json|md`. The
answers describe the sample case PRC-IAM-014 whatever you upload, but the rest
of the pipeline runs as it would in ING: files are stored, answers are
validated against the schema, everything is logged, and a token limit that is
too low fails the same way.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `KCT_AI_PROVIDER` | `gemini` | `gemini`, `anthropic` or `fake` |
| `KCT_AI_MODEL` | per provider | Model name |
| `KCT_TEMPERATURE` | `0` | Gemini sampling temperature. Not sent to Claude: current Claude models reject sampling parameters |
| `KCT_SUMMARY_MAX_TOKENS` | `16384` | Output limit for the two summary agents |
| `KCT_STEPS_MAX_TOKENS` | `32768` | Output limit for the test steps agent |
| `KCT_PROJECT_ID` | | Google Cloud project |
| `KCT_LOCATION` | `europe-west4` | Gemini region |
| `KCT_ANTHROPIC_PLATFORM` | `vertex` | `vertex` or `api` |
| `KCT_ANTHROPIC_REGION` | `europe-west1` | Claude on Vertex AI region |
| `KCT_FILES_DRIVER` | `local` | Where uploads and outputs go: `local` or `gcs` |
| `KCT_GCS_BUCKET` | | Bucket, when `KCT_FILES_DRIVER=gcs` |
| `KCT_GCS_PREFIX` | | Optional folder inside the bucket |
| `KCT_DB_DRIVER` | `sqlite` | Database: `sqlite` or `bigquery` |
| `KCT_DB_PATH` | `<storage>/database.sqlite` | SQLite file |
| `KCT_BQ_DATASET` | | BigQuery dataset: `dataset` (in `KCT_PROJECT_ID`) or `project.dataset` |
| `KCT_BQ_LOCATION` | | Dataset location, e.g. `EU` or `europe-west4`. Empty = BigQuery decides |
| `KCT_STORAGE_ROOT` | `./storage` | Logs; also uploads, outputs and the SQLite file when those are local |
| `KCT_PROMPTS_ROOT` | `./prompts` | Agent instructions |
| `KCT_FIXTURES_ROOT` | `./tests/fixtures/fake_ai` | Fake mode answers |

Thinking tokens count against the output limits. If a call fails with
"answer hit max_tokens", raise the limit for that agent.

## API

All endpoints are under `/api/v1`. Examples assume `localhost:8000`.

### Stage 2: generate test steps — `POST /test-steps`

Multipart upload. Each field takes one or more PDFs (repeat the field for more).

| Field | Content |
|---|---|
| `control_details` | Control details document(s) |
| `test_plan` | Test plan document(s) |

```bash
curl -F control_details=@CD-PRC-IAM-014_Control_Details_v3.2.pdf \
     -F test_plan=@TP-PRC-IAM-014_Test_Plan_2026Q1.pdf \
     http://localhost:8000/api/v1/test-steps
```

Python:

```python
import requests

with open("CD.pdf", "rb") as cd, open("TP.pdf", "rb") as tp:
    r = requests.post(
        "http://localhost:8000/api/v1/test-steps",
        files={"control_details": cd, "test_plan": tp},
        timeout=600,
    )
r.raise_for_status()
print(r.json()["case_id"], len(r.json()["test_steps"]))
```

What happens:

1. The files are stored as a new case: `storage/uploads/case-NNN/`.
2. Three agents run one after another, so expect a minute or more:
   1. `control_details_summary`
   2. `test_plan_summary`
   3. `test_steps`, which reads both raw PDFs
3. The run is saved to the database as a new **case interpretation** with its
   test steps (see Database).
4. Readable copies are written to `storage/outputs/case-NNN/`:
   `control_details_summary.md`, `test_plan_summary.md` and
   `case_interpretation_<id>.json`.
5. Every agent call is logged (see Logs).

Response: metadata header, the two summaries, and the test steps.

```json
{
  "metadata": {
    "case_interpretation_id": "8f14e45f-ceea-467a-9575-0e6f1d9c2b11",
    "case_id": "2c9a7b0e-51d4-4f5e-9d8a-3b6f0e7c1a22",
    "case_reference": "case-002",
    "provider": "gemini",
    "model": "gemini-2.5-pro",
    "created_at": "2026-10-15T09:41:28+00:00",
    "step_count": 17
  },
  "summaries": {
    "control_details": "# Control Details Summary\n...",
    "test_plan": "# Test Plan Summary\n..."
  },
  "test_steps": [
    {
      "id": "d3b07384-d9a0-4c2b-8f3e-5a1c9e7b6f40",
      "case_interpretation_id": "8f14e45f-ceea-467a-9575-0e6f1d9c2b11",
      "case_id": "2c9a7b0e-51d4-4f5e-9d8a-3b6f0e7c1a22",
      "reference": "0472-04",
      "title": "Verification precedes the reset",
      "description": "CTL-IAM-0472. Compare the identity verification timestamp on the EV-01 ticket to the reset execution timestamp in the ADX audit log extract (EV-03).",
      "acceptance_criteria": [
        "The verification timestamp is earlier than the reset execution timestamp.",
        "Verification and reset were performed by the same agent ID."
      ],
      "refusal_criteria": [
        "The reset was executed before verification.",
        "The reset was executed by an agent other than the one who verified."
      ],
      "status": "pending"
    }
  ]
}
```

Metadata fields:

| Field | Meaning |
|---|---|
| `case_interpretation_id` | ID of this run (UUID) |
| `case_id` | ID of the case (UUID) |
| `case_reference` | Case folder name, used in the `/cases/{case_id}/...` URLs |
| `provider`, `model` | What the test steps agent ran on |
| `created_at` | When the run was saved (UTC) |
| `step_count` | Number of test steps |

Test step fields:

| Field | Meaning |
|---|---|
| `id` | ID of the step (UUID), unique across all runs |
| `case_interpretation_id` | The run the step belongs to |
| `case_id` | ID of the case (UUID) |
| `reference` | Test plan step ID as written in the plan. `DERIVED-01`, `DERIVED-02`… for requirements in the control details that no plan step covers |
| `title` | Short name of what the step checks |
| `description` | What to examine and how, including control ID and evidence IDs |
| `acceptance_criteria` | Conditions that must all hold for the step to pass |
| `refusal_criteria` | Conditions under which the step fails |
| `status` | `pending` after Stage 2; Stage 3 sets `effective` or `not_effective` |

Errors:

| Code | When |
|---|---|
| 400 | An upload is not a PDF |
| 404 | Unknown case |
| 422 | `control_details` or `test_plan` is missing |
| 500 | AI provider not configured (for example `KCT_PROJECT_ID` missing) |
| 502 | An agent failed, was cut off by its token limit, or returned output that does not match the schema. The detail starts with the case ID; the files are stored, so retry with the endpoint below |

### Re-run Stage 2 on a stored case — `POST /cases/{case_id}/test-steps`

```bash
curl -X POST http://localhost:8000/api/v1/cases/case-002/test-steps
```

Same response as above. No upload; uses the case's stored PDFs. Each run is a
new case interpretation with new step IDs; earlier runs stay in the database.

### Read saved test steps

| Method and path | Returns |
|---|---|
| `GET /case-interpretations` | Metadata of every case interpretation, newest first. Add `?case_id=case-002` for one case |
| `GET /case-interpretations/{case_interpretation_id}` | One case interpretation: metadata, summaries, test steps |
| `GET /cases/{case_id}/test-steps` | The newest case interpretation of a case |

```bash
curl http://localhost:8000/api/v1/case-interpretations
curl http://localhost:8000/api/v1/case-interpretations/8f14e45f-ceea-467a-9575-0e6f1d9c2b11
curl http://localhost:8000/api/v1/cases/case-002/test-steps
```

## Storage

Two switches, each with a local driver for development and a Google Cloud
driver for ING. Controllers do not know which one runs.

| What | Setting | Local | Google Cloud |
|---|---|---|---|
| Uploaded PDFs and outputs | `KCT_FILES_DRIVER` | `local`: under `KCT_STORAGE_ROOT` | `gcs`: in `KCT_GCS_BUCKET` |
| Case interpretations and test steps | `KCT_DB_DRIVER` | `sqlite`: `storage/database.sqlite` | `bigquery`: in `KCT_BQ_DATASET` |

Logs always stay local in `storage/logs/`.

Files keep the same layout on both disks: `uploads/case-NNN/<kind>/*.pdf` and
`outputs/case-NNN/*`, below `KCT_GCS_PREFIX` in the bucket. Each case also has
an empty `uploads/case-NNN/.case` file that reserves its number, so two
uploads at the same time never get the same case.

### Database tables

The same tables on SQLite and BigQuery:

| Table | One row per | Columns |
|---|---|---|
| `cases` | Uploaded case | `id`, `reference` (case-001), `created_at` |
| `case_interpretations` | Stage 2 run | `id`, `case_id`, `provider`, `model`, `control_details_summary`, `test_plan_summary`, `created_at` |
| `test_steps` | Test step | `id`, `case_interpretation_id`, `case_id`, `position`, `reference`, `title`, `description`, `acceptance_criteria`, `refusal_criteria`, `status`, `created_at`, `updated_at` |

- IDs are UUIDs made when a row is saved, because BigQuery has no
  auto-increment.
- Criteria lists are `ARRAY<STRING>` on BigQuery and JSON text on SQLite.
- Tables are created on first start (`CREATE TABLE IF NOT EXISTS`).
- There are no migrations yet. After a schema change, delete
  `storage/database.sqlite` or drop the BigQuery tables.

### BigQuery and GCS in ING

1. Create the bucket and the dataset, or get their names from the platform
   team. The app does not create them.
2. The account the workbench runs as needs:
   - **Storage Object User** on the bucket.
   - **BigQuery Job User** on the project.
   - **BigQuery Data Editor** on the dataset. It can create tables.
3. Install the packages if they are missing:
   `pip install google-cloud-storage google-cloud-bigquery`.
4. Set these in `.env` and restart uvicorn:

```bash
KCT_FILES_DRIVER=gcs
KCT_GCS_BUCKET=your-bucket
KCT_DB_DRIVER=bigquery
KCT_BQ_DATASET=your_dataset
KCT_BQ_LOCATION=europe-west4
```

Check access from a notebook before switching:

```python
from google.cloud import bigquery, storage
bq = bigquery.Client(project="<project>")
print([d.dataset_id for d in bq.list_datasets()])
print(list(bq.query("SELECT 1 AS ok").result()))
print([b.name for b in storage.Client(project="<project>").list_buckets()])
```

Rows are written with DML `INSERT` in one transaction, not with streaming
inserts. BigQuery cannot update streamed rows for up to 90 minutes, and Stage 3
needs to update each step's status.

To add another backend later, such as Cloud SQL:

1. Add a driver in `services/database/drivers/` (or `services/files/disks/`).
2. Add a branch for it in that folder's `manager.py`.

### Print test steps from the terminal or a notebook

```bash
python scripts/test_steps.py              # list case interpretations
python scripts/test_steps.py <id>         # metadata, then the test steps of one interpretation
python scripts/test_steps.py <id> --json  # the same as JSON
```

In Jupyter, open `notebooks/test_steps.ipynb`, set `CASE_INTERPRETATION_ID`
and run the cells. Or, in any notebook started in the project folder:

```python
%run scripts/test_steps.py <id>

from scripts.test_steps import show, table
show("<id>")     # printed
table("<id>")    # pandas DataFrame, one row per step
```

The script reads through the same driver as the API, so it works on SQLite
and BigQuery. On BigQuery you can also query the tables in the Cloud Console.

### Stage 1: summarize one document — `POST /summarize`

```bash
curl -H 'content-type: application/json' \
     -d '{"case_id": "case-001", "kind": "control_details"}' \
     http://localhost:8000/api/v1/summarize
```

`kind` is `control_details` or `test_plan`. Returns
`{"case_id", "kind", "summary"}` and writes `outputs/<case>/<kind>_summary.md`.

### Other endpoints

| Method and path | Returns |
|---|---|
| `GET /health` | `{"status": "ok", "provider": ..., "model": ...}` |
| `GET /cases` | List of case IDs |
| `GET /cases/{case_id}/files/{kind}` | PDF file names of one kind in a case |

## Logs

| File | Content |
|---|---|
| `storage/logs/app.log` | What the app did: cases stored, one line per agent call (provider, model, tokens, time), steps generated, errors. Also printed to the console |
| `storage/logs/agents.log` | One JSON line per agent call with the full model output |

```bash
tail -f storage/logs/app.log
tail -n 1 storage/logs/agents.log | python -m json.tool
```

## Tests

```bash
python -m unittest discover tests
```

`tests/test_database.py` checks the SQLite repository and the notebook script.
`tests/test_storage_drivers.py` checks the file service and the GCS and BigQuery
drivers, with the Google Cloud calls replaced.
`tests/test_api.py` runs the API end to end with the fake provider in a
temporary storage folder. `tests/test_providers.py` checks what the Gemini and
Claude providers send and how they read answers, with the network call replaced.

## Code layout

Laravel-style: routes bind to controllers, controllers only call services.

```
main.py                         App, logging, exception -> HTTP status mapping
routes/api.py                   Routes bound to controller methods
controllers/
  test_steps_controller.py      Stage 2: store files -> run agents -> save to database -> respond
  case_interpretations_controller.py  Read stored case interpretations
  summary_controller.py         Stage 1
  cases_controller.py           Health, case listings
bootstrap/logging.py            app.log and agents.log
services/
  config.py                     All settings, read from env
  files/
    file_service.py             Case folders, uploads and outputs, on any disk
    disks/                      base.py (contract), local.py, gcs.py, manager.py (KCT_FILES_DRIVER)
  database/                     Stage 2 results
    contracts.py                CaseInterpretationRepository: what every driver offers
    manager.py                  Picks the driver from KCT_DB_DRIVER
    drivers/                    sqlite.py, bigquery.py
  ai/                           Small Python copy of the Laravel AI SDK
    agent.py                    Agent base: instructions(), output_schema, prompt(), fake()
    attachments.py              Document.from_path()
    responses.py                AgentResponse, Usage
    manager.py                  Picks the provider by name
    providers/                  base.py (contract), gemini.py, anthropic.py, fake.py
  control_testing/
    agents/                     One file per agent, e.g. test_steps_agent.py
    data.py                     TestStep, CaseInterpretation and other data shapes
scripts/test_steps.py           Print test steps of a case interpretation
notebooks/test_steps.ipynb      The same in Jupyter
prompts/<agent name>.md         Each agent's instructions
tests/fixtures/fake_ai/         Fake mode answers, one per agent
storage/                        uploads/, outputs/, logs/, database.sqlite (never committed)
```

### Writing an agent

```python
from services.ai.agent import Agent

class EvidenceVerdictAgent(Agent):
    name = "evidence_verdict"          # also the fake fixture name
    max_tokens = 16384
    output_schema = VerdictList        # a pydantic model; omit for plain text
    # provider = "anthropic"           # optional: pin a provider for this agent
    # model = "claude-opus-5-5"        # optional: pin a model

    def instructions(self) -> str:
        return "You are a control testing analyst..."

response = EvidenceVerdictAgent().prompt(
    "Judge each test step against the evidence.",
    attachments=[Document.from_path(path)],
)
response.structured   # validated VerdictList
response.text         # raw answer
```

In tests, `EvidenceVerdictAgent.fake(["...answer..."])` makes the next calls
return those answers without any provider; `stop_faking()` undoes it.
