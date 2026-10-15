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
| `KCT_STORAGE_ROOT` | `./storage` | Uploads, outputs and logs |
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
3. Outputs are written to `storage/outputs/case-NNN/`:
   `control_details_summary.md`, `test_plan_summary.md`, `test_steps.json`.
4. Every agent call is logged (see Logs).

Response:

```json
{
  "case_id": "case-002",
  "summaries": {
    "control_details": "# Control Details Summary\n...",
    "test_plan": "# Test Plan Summary\n..."
  },
  "test_steps": [
    {
      "id": "0472-04",
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

Test step fields:

| Field | Meaning |
|---|---|
| `id` | Test plan step ID as written in the plan. `DERIVED-01`, `DERIVED-02`… for requirements in the control details that no plan step covers |
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

Same response as above. No upload; uses the case's stored PDFs.

### Read saved test steps — `GET /cases/{case_id}/test-steps`

```bash
curl http://localhost:8000/api/v1/cases/case-002/test-steps
```

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

`tests/test_api.py` runs the API end to end with the fake provider in a
temporary storage folder. `tests/test_providers.py` checks what the Gemini and
Claude providers send and how they read answers, with the network call replaced.

## Code layout

Laravel-style: routes bind to controllers, controllers only call services.

```
main.py                         App, logging, exception -> HTTP status mapping
routes/api.py                   Routes bound to controller methods
controllers/
  test_steps_controller.py      Stage 2: store files -> run agents -> save outputs -> respond
  summary_controller.py         Stage 1
  cases_controller.py           Health, case listings
bootstrap/logging.py            app.log and agents.log
services/
  config.py                     All settings, read from env
  files/file_service.py         Uploads and outputs on disk
  ai/                           Small Python copy of the Laravel AI SDK
    agent.py                    Agent base: instructions(), output_schema, prompt(), fake()
    attachments.py              Document.from_path()
    responses.py                AgentResponse, Usage
    manager.py                  Picks the provider by name
    providers/                  base.py (contract), gemini.py, anthropic.py, fake.py
  control_testing/
    agents/                     One file per agent, e.g. test_steps_agent.py
    data.py                     TestStep and other data shapes
prompts/<agent name>.md         Each agent's instructions
tests/fixtures/fake_ai/         Fake mode answers, one per agent
storage/                        uploads/, outputs/, logs/ (never committed)
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
