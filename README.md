# KCT — Key Control Testing

Stage 1: summarize the control details and test plan for a case, using Gemini on
Vertex AI.

## Folder structure

```
kct-ai/
├── kct/                    # the application — all logic lives here
│   ├── config.py           # env-driven settings        (Laravel: config/ + .env)
│   ├── models.py           # Pydantic schemas           (Laravel: Form Requests + DTOs)
│   ├── storage.py          # case paths, hashing, I/O   (Laravel: Storage facade)
│   ├── prompts.py          # versioned prompt loading   (Laravel: Blade view loader)
│   ├── gemini.py           # the only Vertex client     (Laravel: an HTTP client wrapper)
│   ├── cli.py              # terminal entrypoint        (Laravel: artisan command)
│   └── services/
│       └── summarize.py    # stage 1 use case           (Laravel: Action / Service class)
├── routes/
│   └── api.py              # FastAPI router             (Laravel: routes/api.php + controller)
├── prompts/                # versioned prompt files, committed
│   ├── summarize_control_details.v1.md
│   └── summarize_test_plan.v1.md
├── storage/                # runtime data — gitignored
│   ├── cases/
│   │   └── case-001/
│   │       ├── case.json           # manifest: which process, which period
│   │       ├── control_details/    # input PDFs
│   │       ├── test_plan/          # input PDFs
│   │       ├── evidence/           # stage 2 inputs
│   │       └── output/
│   │           ├── control_details_summary.md
│   │           ├── test_plan_summary.md
│   │           └── runs/<run_id>.json   # audit record per model call
│   └── logs/
├── tests/
├── main.py                 # uvicorn entrypoint         (Laravel: public/index.php)
├── requirements.txt
├── .env.example
└── .gitignore
```

### Why this shape

- **`storage/` is gitignored entirely.** In a bank the cost of one real evidence
  file reaching the repo is far higher than the convenience of committed
  fixtures. If you want the synthetic case in version control, copy it to
  `tests/fixtures/` and commit that instead — never loosen the ignore on
  `storage/`.
- **One folder per case, one subfolder per document kind.** The code never
  guesses which file is a test plan; the folder says so. That holds when Pega
  starts dropping files in.
- **`prompts/` is committed and versioned by filename.** `summarize_test_plan.v2.md`
  sits beside `v1`. Every run record names the version and its SHA-256, so a
  verdict can be traced to the exact wording that produced it.
- **Services hold the logic, routes stay thin.** The same `summarize.run()` is
  callable from the API, the CLI and a notebook.

## Setup

```bash
cp .env.example .env        # fill in KCT_PROJECT_ID
pip install -r requirements.txt
```

Upload the two PDFs:

```
storage/cases/case-001/control_details/CD-PRC-IAM-014_Control_Details_v3.2.pdf
storage/cases/case-001/test_plan/TP-PRC-IAM-014_Test_Plan_2026Q1.pdf
```

## Run from the terminal

```bash
python -m kct.cli cases
python -m kct.cli files case-001 control_details
python -m kct.cli summarize case-001 control_details
python -m kct.cli summarize case-001 test_plan --force
```

## Run the API

Port 8080 is taken by JupyterLab, so use 8000:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
curl localhost:8000/api/v1/health
curl localhost:8000/api/v1/cases
curl localhost:8000/api/v1/cases/case-001/files/test_plan

curl -X POST localhost:8000/api/v1/cases/case-001/summarize \
  -H 'Content-Type: application/json' \
  -d '{"kind": "control_details"}'

curl -X POST localhost:8000/api/v1/cases/case-001/summarize \
  -H 'Content-Type: application/json' \
  -d '{"kind": "test_plan", "force": true}'
```

Interactive docs at `http://localhost:8000/docs`.

## Audit trail

Every model call writes `storage/cases/<case_id>/output/runs/<run_id>.json`
containing the model and region, temperature, prompt name, version and SHA-256,
the SHA-256 and size of every input file, token usage, timings, and the error if
it failed. A failed run is still recorded before the exception propagates.

Temperature defaults to 0. A control test that produces a different answer on
re-run is not defensible to a model risk reviewer.

## Not yet built

- Stage 2: evidence extraction (XLSX, MSG) and per-step validation.
- Structured output — stage 1 returns Markdown. If the validator needs JSON,
  switch `response_mime_type` in `gemini.generate()` and add a response schema.
- Persistence beyond the filesystem (GCS for files, BigQuery for run records).
