# KCT

Key Control Testing helper. Takes a process's control details and test plan
(PDF), turns them into test steps, and prepares the evidence for checking them,
using Gemini or Claude.

The process, in the words used everywhere in this project (code, logs, docs):

| Step | What it does | Status |
|---|---|---|
| **Case** | Upload the control details and test plan PDFs; stored as `case-NNN` | done |
| **Interpretation** | Summarize both documents and turn them into test steps with acceptance and refusal criteria (JSON) | done |
| **Evidence** | Upload evidence files per case (Word, Excel, Outlook emails, PDF, images), convert them for the AI and split big ones into parts | done |

(Earlier versions called the interpretation "Stage 1 + 2".)

## Demo: the notebooks in order

Open the notebooks in `notebooks/` and run them by number (Run All in each).
Before starting, set `KCT_DB_DRIVER=sqlite` in `.env` so the results of 04
are still there for 05 and 06. Start with 00 to get a clean slate. Everything runs with the fake AI unless `.env`
says otherwise.

| # | Notebook | Shows |
|---|---|---|
| 00 | `00_cleanup.ipynb` | Clean slate: shows, then deletes, the database, converted evidence, fake samples and demo leftovers |
| 01 | `01_setup.ipynb` | Python and packages are fine, settings, AI smoke test, tests, API start/stop |
| 02 | `02_hello.ipynb` | One question to the AI ("What is 5+2?") through the app's services |
| 03 | `03_sqlite_test.ipynb` | SQLite works: writes and shows a few records |
| 04 | `04_demo_data.ipynb` | Interpretation end to end: two PDFs in, summaries and 17 test steps saved to the database |
| 05 | `05_test_steps.ipynb` | The test steps of a run, as text, table and JSON |
| 06 | `06_database.ipynb` | The database as tables, without a database GUI |
| 07 | `07_evidence_word_to_pdf.ipynb` | Word evidence to PDF, so the AI can read it |
| 08 | `08_evidence_excel.ipynb` | Excel evidence to text with Excel coordinates, colors and comments, plus pictures |
| 09 | `09_evidence_email.ipynb` | Outlook emails (.msg) to text; their Word, Excel and email attachments converted too |
| 10 | `10_evidence_case.ipynb` | Evidence of one case: upload, convert, split into the parts the assessment will send (calls and tokens) |

## Ways to run it

| Where | Needs | API | Notebooks |
|---|---|---|---|
| Docker on your computer | Docker Desktop only | `docker compose up api` | `docker compose up jupyter`, or VS Code |
| Python on your computer | Python 3.9+ | `uvicorn ...` | `jupyter lab`, or VS Code |
| Vertex AI Workbench (ING, or a personal project) | A workbench instance | Terminal in JupyterLab | JupyterLab, or VS Code if allowed |

Try everything first without any cloud access: `KCT_AI_PROVIDER=fake`. The
smoke test is `POST /api/v1/ask` or `notebooks/02_hello.ipynb`, both asking
"What is 5+2?". In fake mode the answer is always `5 + 2 = 7.`; with a real
provider the response also shows which model answered and how many tokens it
used.

### Setup with play buttons: `notebooks/01_setup.ipynb`

Prefer JupyterLab to a terminal? Open `notebooks/01_setup.ipynb` and press ▶ on
each cell, top to bottom. It does everything `kct.sh` does: checks Python and
packages, installs what is missing, shows the settings, asks "What is 5+2?",
checks SQLite, runs the tests, and starts and stops the API. Settings go in
its first cell (or in `.env`).

### One script for all commands: `kct.sh`

The same from a terminal: every command in this README is in `kct.sh`, so nothing has to be copied by hand. In a JupyterLab terminal,
from the project folder:

```bash
chmod +x kct.sh              # once
./kct.sh install             # notebook packages, only what is missing
./kct.sh install --api       # plus the API packages
./kct.sh check               # what is installed, which settings are active
./kct.sh ask                 # smoke test: "What is 5+2?"
./kct.sh sqlite              # check SQLite works (writes storage/sqlite_test.sqlite)
./kct.sh api                 # start the API on port 8000 (./kct.sh api 8010 for another)
./kct.sh curl                # in a second terminal: call /health and /ask
./kct.sh steps               # list case interpretations
./kct.sh test                # run the tests
```

It loads `.env` when there is one. Without `.env` it runs in fake mode.
For an internal pip mirror: `export KCT_PIP_INDEX=<mirror-url>` before
`./kct.sh install`.

## Run with Docker (no local Python needed)

1. Install Docker Desktop and start it.
2. Optional: `cp .env.example .env` and fill it in. Without `.env` everything
   runs in fake mode. Docker Compose reads `.env` itself; no `source` needed.
3. Build once (again after changing `requirements.txt`):

   ```bash
   docker compose build
   ```

4. Start what you need, from the project folder:

   ```bash
   docker compose up api        # http://localhost:8000/docs
   docker compose up jupyter    # http://localhost:8888, open notebooks/02_hello.ipynb
   docker compose up            # both
   ```

5. Stop with Ctrl+C, or `docker compose down`.

Port taken (for example by `php artisan serve` on 8000)? Pick others, on the
command line or in `.env`:

```bash
KCT_API_PORT=8010 KCT_JUPYTER_PORT=8890 docker compose up
```

Laravel Herd itself only uses ports 80 and 443, so it does not clash.

The project folder is mounted into the containers, so code changes apply
without a rebuild (the API reloads by itself; in Jupyter restart the kernel),
and `storage/` lands in your project folder as usual.

Google credentials for Gemini or Claude on Vertex AI: the containers read your
gcloud login from `~/.config/gcloud`. Log in once on your computer. Without a
local gcloud, log in through a container instead:

```bash
docker run --rm -it -v ~/.config/gcloud:/root/.config/gcloud \
  gcr.io/google.com/cloudsdktool/google-cloud-cli:stable \
  gcloud auth application-default login
```

## Run with Python

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # skip what the workbench already has
pip install jupyterlab               # only for notebooks outside a workbench
cp .env.example .env                 # then fill it in
```

The app reads `.env` from the project folder by itself (API, notebooks,
`kct.sh`). Variables already set in the shell or in a notebook cell win over
it. `KCT_ENV_FILE=<path>` reads another file; `KCT_ENV_FILE=` turns it off.

No vim or nano needed to edit it:

- In JupyterLab: **File > Open from Path...**, type `.env`, and it opens in
  JupyterLab's text editor. Save with Ctrl+S. To see dot files in the file
  browser: **View > Show Hidden Files**.
- Or fill in Step 1 of `notebooks/01_setup.ipynb` and run Step 1b: it writes the
  values into `.env` (creating it from `.env.example` if needed).
- In VS Code: open the project folder; `.env` is in the file list.

Gemini and Claude on Vertex AI use Google Application Default Credentials. On
a Vertex AI Workbench this works out of the box; elsewhere run
`gcloud auth application-default login`.

API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs (interactive docs, try every endpoint there),
or test from the terminal:

```bash
curl -X POST -H 'Content-Type: application/json' \
     -d '{"question": "What is 5+2?"}' http://localhost:8000/api/v1/ask
```

Notebooks: run `jupyter lab` in the project folder and open
`notebooks/02_hello.ipynb`, then Run > Run All Cells. The notebooks call the
services directly, so the API does not need to be running.

## Run on Windows

Works the same, with three differences:

- `kct.sh` is a bash script and does not run in the Windows command prompt or
  PowerShell. Use `notebooks/01_setup.ipynb` instead (it does the same), or Git Bash.
- Python commands:
  ```bat
  py -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  ```
  `.env` needs no exporting: the app reads it itself.
- Gemini needs a Google login on the laptop: install the Google Cloud CLI for
  Windows and run `gcloud auth application-default login` once. If that is not
  allowed, ask the platform team how laptops reach Vertex AI.

## Run on Vertex AI Workbench (as in ING)

Docker is for your own computer only. In ING there is no Docker: the
workbench already has Python and JupyterLab, and you install the few
packages with pip.

What to install in ING, and what not:

| Package | Needed for | Install? |
|---|---|---|
| Python 3.9+, JupyterLab, `sqlite3` | Everything | No: on the workbench already (`sqlite3` is part of Python) |
| `pydantic` | Everything | Usually there already; must be version 2.x (`pip install --user "pydantic>=2"` if 1.x) |
| `google-genai` | Gemini (`KCT_AI_PROVIDER=gemini`) | Yes, if missing |
| `pandas` | `06_database.ipynb`, `table()` | Usually there already |
| `python-docx`, `reportlab` | `07_evidence_word_to_pdf.ipynb` (.docx to PDF) | Yes, if missing (pure pip, no LibreOffice needed) |
| `openpyxl` | `08_evidence_excel.ipynb` (Excel to text) | Yes, if missing |
| `extract-msg` | `09_evidence_email.ipynb` (.msg emails). GPL-3.0 | Yes, if missing; check the license with ING first |
| `pypdf` | Splitting large evidence PDFs | Yes, if missing |
| `fastapi`, `uvicorn`, `python-multipart` | Only the API | Only if you run the API |
| `anthropic[vertex]` | Only Claude | Only if you use Claude |
| `google-cloud-storage`, `google-cloud-bigquery` | Only `gcs` / `bigquery` drivers | Not now (no storage approved) |
| `httpx` | Only the tests | No |

1. Open the workbench's JupyterLab and clone or upload the project folder.
2. In a JupyterLab terminal, from the project folder:

   ```bash
   pip list | grep -i -E "pydantic|google-genai|pandas|fastapi|uvicorn|multipart"
   pip install --user google-genai pydantic python-docx reportlab openpyxl extract-msg pypdf   # notebooks
   pip install --user fastapi uvicorn python-multipart   # only for the API
   ```

   Install only what the first command does not list. If pip cannot reach
   PyPI, ask the platform team for the internal mirror and set it with
   `pip config set global.index-url <mirror-url>`. After installing, restart
   the notebook kernel.
3. Notebooks: open `notebooks/02_hello.ipynb`. It reads `.env`; or set the
   variables in the first cell, before `boot()`:

   ```python
   os.environ["KCT_AI_PROVIDER"] = "gemini"
   os.environ["KCT_PROJECT_ID"] = "<project>"
   ```

   Run all cells. Settings are read once per kernel, so after changing a
   variable restart the kernel (Kernel > Restart Kernel).
4. API: in a JupyterLab terminal run
   `uvicorn main:app --host 0.0.0.0 --port 8000` (it reads `.env` itself),
   or use Step 8 of `notebooks/01_setup.ipynb`. Open it through the
   JupyterLab proxy: `https://<workbench-url>/proxy/8000/docs`.

## Notebooks in VS Code

What you need:

1. VS Code with two extensions: **Python** and **Jupyter** (both by
   Microsoft).
2. A Python kernel that has the project's packages. One of:
   - **Docker** (no local Python): run `docker compose up jupyter`, then in
     VS Code open a notebook, click **Select Kernel** (top right) >
     **Existing Jupyter Server**, enter `http://localhost:8888`, and pick
     **Python 3**.
   - **Local Python**: create `.venv` as in "Run with Python", also
     `pip install ipykernel`, then **Select Kernel** > **Python
     Environments** > `.venv`.
3. Open the project folder itself in VS Code (File > Open Folder), so the
   notebooks find `services/`.
4. Settings: the notebooks read the project's `.env` themselves; values set
   in a notebook cell before `boot()` win over it.
5. Google credentials: `gcloud auth application-default login` on your
   computer (or the Docker command above). Not needed in fake mode.

In ING, VS Code would have to reach the Vertex AI Workbench instead of a local
kernel. Ask the platform team first:

- Whether VS Code may connect to the workbench at all (some setups only allow
  the browser JupyterLab), and which way: the workbench's own Code editor,
  Remote - SSH, or a remote Jupyter server URL.
- Whether installing the Python and Jupyter extensions is allowed on the ING
  laptop.
- Whether `pip install` from PyPI works on the workbench, or packages come
  from an internal mirror (then set `pip config set global.index-url <mirror>`).
- Which project ID and region to use (`KCT_PROJECT_ID`, `KCT_LOCATION`), and
  whether Gemini (and Claude, if wanted) is enabled for the project in
  Vertex AI.
- Where documents may be stored. Until that is approved, keep
  `KCT_FILES_DRIVER=local` and `KCT_DB_DRIVER=memory`.

## Testing on a personal Google Cloud project

Before ING approves anything, the same code runs on a private Google Cloud
project with a few euros of credit. Use only sample documents there, never
real ING documents or evidence.

1. In the Google Cloud console create a project and link billing (the
   credit). Set a budget alert under Billing > Budgets & alerts, for example
   at 5 EUR.
2. Enable the Vertex AI API: APIs & Services > Enable APIs and services >
   "Vertex AI API".
3. Pick where to run it:
   - **Your computer, with Docker** (cheapest; only model calls are billed).
     Log in with the Docker command in "Run with Docker", then put this in
     `.env` and run `docker compose up`:

     ```bash
     KCT_AI_PROVIDER=gemini
     KCT_PROJECT_ID=<project>
     KCT_LOCATION=europe-west4
     ```

   - **Cloud Shell** (button `>_` top right in the console; free, has Python
     and Docker, nothing to install). Clone the project, then
     `pip install -r requirements.txt`, export the three variables above and
     run `uvicorn main:app --port 8080`. Open it with Web Preview > Preview
     on port 8080, then add `/docs` to the URL.
   - **Vertex AI Workbench**, closest to ING: Vertex AI > Workbench > Create
     new, smallest machine type, then follow "Run on Vertex AI Workbench". A
     workbench is billed per hour while it runs, so stop it when you are done.
4. Smoke test with `/ask` or `notebooks/02_hello.ipynb` first: a question costs a
   fraction of a cent. An interpretation (three calls with two PDFs on Gemini 2.5
   Pro) costs a few cents, depending on document size and thinking tokens.
   `storage/logs/agents.log` has the token counts of each call.

Start with Gemini. Claude needs extra steps: enable the model in Vertex AI
Model Garden and check its region.

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
| `KCT_DB_DRIVER` | `memory` | Database: `memory` (nothing stored), `sqlite` or `bigquery` |
| `KCT_DB_PATH` | `<storage>/database.sqlite` | SQLite file |
| `KCT_BQ_DATASET` | | BigQuery dataset: `dataset` (in `KCT_PROJECT_ID`) or `project.dataset` |
| `KCT_BQ_LOCATION` | | Dataset location, e.g. `EU` or `europe-west4`. Empty = BigQuery decides |
| `KCT_EVIDENCES_ROOT` | `<storage>/evidences` | Evidence documents (assessment). Any folder layout below it |
| `KCT_PDF_MAX_PAGES` | `50` | Evidence PDFs with more pages are split into parts |
| `KCT_PDF_MAX_MB` | `20` | Evidence PDFs (or parts) bigger than this are split further |
| `KCT_PDF_OVERLAP_PAGES` | `2` | Pages repeated at each cut, so nothing is lost at a page break |
| `KCT_EVIDENCE_MAX_TOKENS` | `300000` | Estimated tokens per part; bigger evidence is split |
| `KCT_STORAGE_ROOT` | `./storage` | Logs; also uploads, outputs and the SQLite file when those are local |
| `KCT_PROMPTS_ROOT` | `./prompts` | Agent instructions |
| `KCT_FIXTURES_ROOT` | `./tests/fixtures/fake_ai` | Fake mode answers |

Thinking tokens count against the output limits. If a call fails with
"answer hit max_tokens", raise the limit for that agent.

## Using the services from a notebook

All work lives in services; the API controllers only translate HTTP to service
calls. `services/app.py` builds every service once, and both `routes/api.py`
and notebooks use it, so a notebook runs exactly the code the API runs.

```python
from services.app import boot

kct = boot()                                   # reads KCT_* env vars, sets up logging
kct.ask.ask("What is 5+2?").answer             # smoke test of the AI provider
case_id = kct.interpretations.create_case(["CD.pdf"], ["TP.pdf"])
interpretation = kct.interpretations.generate(case_id)
kct.summaries.summarize(case_id, DocumentKind.TEST_PLAN)
kct.database.interpretations()
```

| Service | API |
|---|---|
| `kct.ask.ask(question)` | `POST /ask` |
| `kct.summaries.summarize(case_id, kind)` | `POST /summarize` |
| `kct.interpretations.create_and_generate(cd, tp)` | `POST /test-steps` |
| `kct.interpretations.generate(case_id)` | `POST /cases/{case_id}/test-steps` |
| `kct.interpretations.latest(case_id)` | `GET /cases/{case_id}/test-steps` |

Settings are read once per kernel: set `KCT_*` variables before `boot()`, or
restart the kernel after changing them.

Notebooks in `notebooks/`:

- `00_cleanup.ipynb`: clean slate before a demo. Lists what would be deleted
  (database, stored cases, converted evidence, fake samples, demo leftovers,
  logs), and deletes only after `CONFIRM = True`. See "Cleaning up".
- `01_setup.ipynb`: set up and check everything with ▶ buttons, no terminal
  (see "Setup with play buttons").
- `02_hello.ipynb`: asks "What is 5+2?" through `AskService`. Runs in fake mode
  unless `KCT_AI_PROVIDER` is set.
- `05_test_steps.ipynb`: reads stored test steps from the database.
- `04_demo_data.ipynb`: runs one interpretation with the fake AI on two placeholder
  PDFs and saves it, so `06_database.ipynb` and `05_test_steps.ipynb` have records
  to show. Use with `KCT_DB_DRIVER=sqlite`.
- `07_evidence_word_to_pdf.ipynb`: converts evidence Word files (`.docx`) in the
  evidences folder to PDF, because Gemini and Claude read PDFs, not `.docx`.
  Can create a sample evidence file first. See "Evidence files".
- `08_evidence_excel.ipynb`: converts Excel evidence for the AI: sheets as text
  with Excel coordinates, colors and comments, pictures as images. Can create
  a fake ING-style workbook first. See "Excel evidence".
- `09_evidence_email.ipynb`: converts Outlook emails (`.msg`) for the AI: the
  email as text (header, body with lists, red text and inline images) and its
  attachments through the Word, Excel and email converters. Can create a fake
  evidence email first. See "Email evidence".
- `10_evidence_case.ipynb`: puts evidence into a case's folder and shows
  how it is converted and split into parts, one per future AI call, with
  token estimates. See "Evidence of a case".
- `03_sqlite_test.ipynb`: checks SQLite works on the machine. Creates
  `storage/sqlite_test.sqlite`, writes three records and shows them. Needs
  only Python; does not touch the app's database.
- `06_database.ipynb`: browses the SQLite file (`KCT_DB_DRIVER=sqlite`) without
  any web page. Lists tables and row counts, shows interpretations and test
  steps, and runs any SQL you type, each result as a table in the notebook.
  Opens the file read-only. Needs pandas.

No browser GUI (as on the ING machine)? Use only the notebooks and the
terminal: the notebooks call the services directly, `06_database.ipynb` replaces
a database GUI, and the API is reachable with `curl` from a JupyterLab
terminal (`curl http://localhost:8000/api/v1/health`) even when `/docs` cannot
be opened.

## API

All endpoints are under `/api/v1`. Examples assume `localhost:8000`.

### Interpretation: generate test steps — `POST /test-steps`

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
| `status` | `pending` after the interpretation; the assessment sets `effective` or `not_effective` |

Errors:

| Code | When |
|---|---|
| 400 | An upload is not a PDF |
| 404 | Unknown case |
| 422 | `control_details` or `test_plan` is missing |
| 500 | AI provider not configured (for example `KCT_PROJECT_ID` missing) |
| 502 | An agent failed, was cut off by its token limit, or returned output that does not match the schema. The detail starts with the case ID; the files are stored, so retry with the endpoint below |

### Re-run the interpretation on a stored case — `POST /cases/{case_id}/test-steps`

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
| Case interpretations and test steps | `KCT_DB_DRIVER` | `memory` (default): nothing stored. `sqlite`: `storage/database.sqlite` | `bigquery`: in `KCT_BQ_DATASET` |

Logs always stay local in `storage/logs/`.

No database is approved yet, so the default is `memory`: nothing is written
to any database, and stored test steps can be read back (API, notebook) only
until the API or the notebook kernel restarts. The readable copies in
`outputs/case-NNN/` stay. The SQLite and BigQuery drivers are kept for later;
switch with `KCT_DB_DRIVER`.

Files keep the same layout on both disks: `uploads/case-NNN/<kind>/*.pdf` and
`outputs/case-NNN/*`, below `KCT_GCS_PREFIX` in the bucket. Each case also has
an empty `uploads/case-NNN/.case` file that reserves its number, so two
uploads at the same time never get the same case.

### Database tables

The same tables on SQLite and BigQuery:

| Table | One row per | Columns |
|---|---|---|
| `cases` | Uploaded case | `id`, `reference` (case-001), `created_at` |
| `case_interpretations` | Interpretation run | `id`, `case_id`, `provider`, `model`, `control_details_summary`, `test_plan_summary`, `created_at` |
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
inserts. BigQuery cannot update streamed rows for up to 90 minutes, and the assessment
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

In Jupyter, open `notebooks/05_test_steps.ipynb`, set `CASE_INTERPRETATION_ID`
and run the cells. Or, in any notebook started in the project folder:

```python
%run scripts/test_steps.py <id>

from scripts.test_steps import show, table
show("<id>")     # printed
table("<id>")    # pandas DataFrame, one row per step
```

The script reads through the same driver as the API, so it works on SQLite
and BigQuery. On BigQuery you can also query the tables in the Cloud Console.

### One summary only (part of the interpretation) — `POST /summarize`

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

## Evidence files

Evidence for the assessment goes into `storage/evidences/` (or `KCT_EVIDENCES_ROOT`).
The production folder layout is not known yet, so any structure below it
works: files are found in subfolders too.

Gemini and Claude read PDF documents, not Word files, so `.docx` evidence is
converted to PDF first. `notebooks/07_evidence_word_to_pdf.ipynb` does that with
▶ buttons; from code:

```python
kct.evidences.files()                                   # every file, relative to the folder
kct.evidences.convert("EV-01.docx")                     # Word or Excel, picks the converter
kct.evidences.convert_all()                             # every file without an up-to-date output
kct.evidences.attachments()                             # what the AI can read, as attachments

kct.docx_converter.convert(Path("x.docx"))              # the converters on their own,
kct.excel_converter.convert(Path("y.xlsx"))             # for any file, also outside the folder
```

The logic is in two services, `DocxConverter` (`services/evidences/docx_converter.py`)
and `ExcelConverter` (`services/evidences/excel_converter.py`). `EvidenceService`
only finds the files and hands each to the right converter.

Two engines, picked by `engine="auto"`:

| Engine | Used when | Result |
|---|---|---|
| `libreoffice` | LibreOffice (`soffice`) is installed | Exact Word layout |
| `python` | Otherwise. Needs only `python-docx` and `reportlab` | Text, headings, bold/italic, lists, tables and pictures. Not the exact layout: columns, text boxes, headers and footers are dropped |

The `python` engine uses DejaVu (on most Linux workbenches) or Arial (macOS)
for the text, and falls back to reportlab's built-in Vera font, which has no
letters beyond Western European ones. If accented letters come out as boxes on
the workbench, ask for the `fonts-dejavu` package or LibreOffice.

`python scripts/make_sample_evidence.py` writes made-up samples of each kind
with the factories (see "Fake evidence: factories").

### Excel evidence

Gemini on Vertex AI accepts PDF, plain text and images, not Excel; Claude the
same. ING evidence workbooks have 10 to 40 columns and 1 to 5 sheets, often
with colored rows, comments and pasted screenshots. What works best for that
(research summary: text formats for tables beat images for exact values;
Markdown and HTML beat CSV; models read values off rendered pages poorly):

| Sent to the AI | Made by | For |
|---|---|---|
| `<name>.xlsx.md` | openpyxl (pip) | Exact values. Every sheet as a Markdown table with Excel column letters and row numbers, so the AI cites "F14". Colors, comments, merged cells, hidden rows/columns/sheets and uncalculated formulas written next to the value: `{row fill: light red}`, `{text: red}`, `{comment: "..."}`, `(hidden)` |
| `<name>.xlsx_images/*.png` | openpyxl | Screenshots pasted into the sheets, as images. The text says which cell each sits at |
| `<name>.xlsx.pdf` | LibreOffice, only when installed | The look: every sheet landscape, fitted to the page width. Shows charts and conditional-formatting colors, but 30+ columns come out too small to read values from; that is what the `.md` is for |

```python
kct.evidences.convert_excel("EV-03.xlsx")    # one workbook
kct.evidences.convert_all_excel()            # every workbook without an up-to-date .md
kct.excel_converter.convert(Path("y.xlsx"))  # the converter on its own
kct.evidences.attachments()                  # PDFs, workbook texts and pictures, ready for the AI
```

`notebooks/08_evidence_excel.ipynb` does the same with ▶ buttons and shows the
text the AI gets. Without LibreOffice these are not covered: charts, colors
set by conditional formatting (the text flags the ranges), and formulas in a
file never saved by Excel (shown as the formula). A sheet of 40 columns and
1,000 rows is roughly 100,000 to 200,000 tokens; the notebook prints an
estimate per workbook.

Test before relying on it: ask the model questions with known answers about
2 or 3 real (anonymized) ING workbooks, with the text only, the PDF only and
both, and keep what answers correctly.

The fake workbook from `ExcelFactory` has what real ones
tend to have: 4 sheets (one hidden), a 20-column, 100-row table with a merged title,
light red exception rows and red text, reviewer comments, a hidden column and
row, a two-level merged header, a form-style summary with formulas and
conditional formatting, and a pasted screenshot.

### Evidence of a case

Evidence belongs to a case and lives in `storage/evidences/<case>/`, with any
subfolders below. Upload it through the API or drop files into the folder.

| Method and path | Does |
|---|---|
| `POST /cases/{case_id}/evidences` | Upload: multipart field `files` (repeat for more), optional form field `folder` for a subfolder. Same name replaces the earlier file (`"replaced": true`) |
| `GET /cases/{case_id}/evidences` | The uploaded files: path, kind, size, date |
| `GET /cases/{case_id}/evidences/parts` | Converts and splits everything, and lists the parts the assessment will send, with estimated tokens |

```bash
curl -F files=@EV-01.docx -F files=@EV-03.xlsx -F folder=q1 \
     http://localhost:8000/api/v1/cases/case-002/evidences
curl http://localhost:8000/api/v1/cases/case-002/evidences/parts
```

Accepted: `.docx`, `.xlsx`, `.xlsm`, `.msg`, `.pdf`, `.png`, `.jpg`,
`.jpeg`, `.gif`, `.webp`, `.txt`, `.csv`. Anything else is refused (400), as
are empty files; unknown cases give 404. File and folder names are cleaned, so
an upload can never leave the case's folder.

**Units and parts.** Each uploaded file is one *unit*. An email is one unit
together with its attachments, so the model sees the approval in the email
next to the log attached to it. A unit that is too big for one call is split
into *parts* (`EvidenceSplitter`, `services/evidences/evidence_splitter.py`):

| Kind | Split |
|---|---|
| PDF (also Word, after conversion) | Over `KCT_PDF_MAX_PAGES` pages or `KCT_PDF_MAX_MB`: page ranges with `KCT_PDF_OVERLAP_PAGES` pages repeated at each cut; titles keep the real pages, e.g. `EV-05.pdf (pages 49-98 of 120)`. A range still too big in MB is halved |
| Excel | By sheet, then by row blocks under `KCT_EVIDENCE_MAX_TOKENS`, with the workbook heading and table header repeated in every block; pictures go with their sheet |
| Email | The email text goes with every part; attachments are packed into parts |
| Text, images | Text by lines; images are never split |

Small pieces are packed together, so a unit that fits is one part. Why 50
pages when Gemini accepts far more: accuracy drops deep inside long
documents, and the answer for all test steps must fit the output limit. Tune
the limits after the first real runs.

```python
case = kct.evidences.case("case-002")
case.store([UploadedFile(name="EV-01.docx", data=...)], folder="q1")
case.units()      # one per uploaded file, converted
case.parts()      # split, as the assessment will send them
```

### Email evidence

Evidence often arrives as Outlook emails (`.msg`): approvals, confirmations,
forwarded reports. The models cannot open `.msg`, so `MsgConverter`
(`services/evidences/msg_converter.py`) turns an email into:

| Output | Contents |
|---|---|
| `<name>.msg.md` | Header table (From, To, Cc, date, subject, number of earlier emails); the body, from the HTML version when there is one, keeping lists, tables, colored text (`{text: red}`), links as `text (url)` and where inline images sit (`[inline image: x.png]`); every earlier email quoted in the thread as its own section (`### Earlier email 2 of 5`), found by Outlook's From/Sent block (English, Dutch, German, French); a numbered list of attachments with what each became |
| `<name>.msg_attachments/` | Every attachment, converted by the matching service: Word to PDF, Excel to text + pictures, attached emails to their own `.msg.md` (up to 3 levels deep). PDFs, images and text files are kept as they are. Other formats (`.zip`, `.doc`, `.xls`, `.pptx`) are listed but not sent |

```python
kct.evidences.convert("EV-04.msg")            # or kct.evidences.convert_email(...)
kct.msg_converter.convert(Path("x.msg"))      # the converter on its own
```

A broken attachment never fails the whole email; the list says why it was
skipped. Encrypted or signed emails (S/MIME) may not open.

`.msg` is read with `extract-msg`, which is **GPL-3.0** licensed. Using it
internally is normally fine, but check it against ING's rules for open-source
licenses before production.

### Fake evidence: factories

`factories/` (Laravel: `database/factories`) makes fake evidence files for
demos and tests, with made-up data for the sample case:

| Factory | Makes |
|---|---|
| `DocxFactory` | `EV-01_..._SAMPLE.docx`: headings, a list, a table, a screenshot |
| `ExcelFactory(rows=100)` | `EV-03_..._SAMPLE.xlsx`: 4 sheets (one hidden), 20 columns, colored exception rows, comments, hidden parts, formulas, conditional formatting, a pasted screenshot |
| `PdfFactory(pages=120)` | `EV-05_..._SAMPLE.pdf`: a long ticket log export, every 10th page with a screenshot; for trying out splitting |
| `MsgFactory(history=2, images=1, links=True, attachments=True)` | `EV-04_..._SAMPLE.msg`: the newest reply in an evidence thread with `history` earlier emails quoted below it (Outlook From/Sent/To/Subject blocks), `images` inline screenshots spread over the thread (`image001.png`, ...), ServiceNow/portal/SharePoint links, and the Word file, an Excel extract and a forwarded approval email attached |

```python
from factories import DocxFactory, ExcelFactory, MsgFactory

DocxFactory().create(folder)          # writes the file, returns its path
ExcelFactory(rows=15).make()          # the file as bytes
MsgFactory(history=6, images=3).create(folder)   # a longer thread
```

`python scripts/make_sample_evidence.py` writes all three into the evidences
folder.

## Cleaning up

`notebooks/00_cleanup.ipynb` (or `CleanupService` in
`services/maintenance/cleanup_service.py`) removes what demos and test runs
leave behind. Choose groups, look at the list, then confirm:

| Group | Deletes | Default in the notebook |
|---|---|---|
| `database` | The SQLite file: all case interpretations and test steps | on |
| `evidence_outputs` | What the converters made: PDFs next to `.docx`, `.xlsx.md`, `.msg.md`, `*_images`, `*_attachments` | on |
| `evidence_samples` | The fake files from the factories (`*_SAMPLE.*`) | on |
| `demo_files` | `storage/demo/`, `sqlite_test.sqlite`, `api_from_notebook.log` | on |
| `cases` | `uploads/` and `outputs/`: every stored case, real uploaded PDFs included | off |
| `logs` | `storage/logs/` | off |
| `evidence_all` | Everything in the evidences folder, real evidence included | off |

Nothing is deleted while `CONFIRM = False`. Only paths inside
`KCT_STORAGE_ROOT` and `KCT_EVIDENCES_ROOT` are ever deleted; a BigQuery
dataset or a GCS bucket is never touched (listed as skipped). After deleting
the database, restart the kernels of other open notebooks and the API.

```python
from services.maintenance.cleanup_service import CleanupService
cleanup = CleanupService(settings())
plan = cleanup.plan(["database", "evidence_outputs"])   # deletes nothing
cleanup.run(plan)
```

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

Tests for optional packages that are not installed are skipped, not failed:
the API tests without `fastapi`/`httpx`/`python-multipart`, the Claude tests
without `anthropic`, the GCS and BigQuery tests without the Google Cloud packages.

`tests/test_database.py` checks the SQLite and memory repositories and the notebook script.
`tests/test_storage_drivers.py` checks the file service and the GCS and BigQuery
drivers, with the Google Cloud calls replaced.
`tests/test_api.py` runs the API end to end with the fake provider in a
temporary storage folder. `tests/test_providers.py` checks what the Gemini and
Claude providers send and how they read answers, with the network call replaced.

## Code layout

Laravel-style: routes bind to controllers, controllers only call services.
All work is in services, built once by `services/app.py` for the API and notebooks.

```
main.py                         App, logging, exception -> HTTP status mapping
routes/api.py                   Routes bound to controller methods
controllers/
  test_steps_controller.py      Interpretation over HTTP (InterpretationService does the work)
  ask_controller.py             POST /ask smoke test
  evidences_controller.py       Evidence of a case: upload, list, parts
  case_interpretations_controller.py  Read stored case interpretations
  summary_controller.py         One summary (part of the interpretation)
  cases_controller.py           Health, case listings
bootstrap/logging.py            app.log and agents.log
services/
  app.py                        boot(): builds every service; used by routes/api.py and notebooks
  config.py                     All settings, read from env
  playground/ask_service.py     AskService: one question to the provider (smoke test)
  maintenance/cleanup_service.py  CleanupService: deletes demo and test leftovers, plan first
  evidences/
    evidence_service.py         EvidenceService: evidence per case, upload, units, converter choice, parts
    units.py                    EvidenceUnit: one uploaded file (an email with its attachments); what counts as evidence
    evidence_splitter.py        EvidenceSplitter: units into parts (PDF pages/MB, Excel sheets/rows, email)
    docx_converter.py           DocxConverter: Word to PDF (LibreOffice, or python-docx + reportlab)
    excel_converter.py          ExcelConverter: Excel to Markdown text + pictures (+ PDF with LibreOffice)
    msg_converter.py            MsgConverter: Outlook email to text; attachments through the other converters
    libreoffice.py              Optional LibreOffice helper shared by both converters
  files/
    file_service.py             Case folders, uploads and outputs, on any disk
    disks/                      base.py (contract), local.py, gcs.py, manager.py (KCT_FILES_DRIVER)
  database/                     Interpretation results
    contracts.py                CaseInterpretationRepository: what every driver offers
    manager.py                  Picks the driver from KCT_DB_DRIVER
    drivers/                    memory.py (default), sqlite.py, bigquery.py
  ai/                           Small Python copy of the Laravel AI SDK
    agent.py                    Agent base: instructions(), output_schema, prompt(), fake()
    attachments.py              Document.from_path()
    responses.py                AgentResponse, Usage
    manager.py                  Picks the provider by name
    providers/                  base.py (contract), gemini.py, anthropic.py, fake.py
  control_testing/
    interpretation_service.py   Interpretation: store case, run agents, save interpretation
    summary_service.py          One summary (part of the interpretation)
    agents/                     One file per agent, e.g. test_steps_agent.py
    data.py                     TestStep, CaseInterpretation and other data shapes
scripts/test_steps.py           Print test steps of a case interpretation
factories/                      DocxFactory, ExcelFactory, MsgFactory, PdfFactory: fake evidence files
scripts/make_sample_evidence.py Write the fake evidence files with the factories
notebooks/                      Demo notebooks, run them in order:
  00_cleanup.ipynb              Clean slate (shows the list, deletes after CONFIRM)
  01_setup.ipynb                Setup and checks, one cell per step (no terminal needed)
  02_hello.ipynb                Asks "What is 5+2?" through AskService
  03_sqlite_test.ipynb          Checks SQLite works: writes and shows a few records
  04_demo_data.ipynb            Fake interpretation that fills the database with demo records
  05_test_steps.ipynb           Print stored test steps
  06_database.ipynb             Browse the SQLite database as tables
  07_evidence_word_to_pdf.ipynb Evidence .docx to PDF
  08_evidence_excel.ipynb       Evidence Excel to text + images for the AI
  09_evidence_email.ipynb       Outlook emails to text, attachments converted
  10_evidence_case.ipynb        Evidence of a case: upload, convert, split into parts
prompts/<agent name>.md         Each agent's instructions
tests/fixtures/fake_ai/         Fake mode answers, one per agent
kct.sh                          All setup and run commands without Docker
Dockerfile, docker-compose.yml  API and JupyterLab containers
storage/                        uploads/, outputs/, evidences/, logs/, database.sqlite if sqlite (never committed)
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
