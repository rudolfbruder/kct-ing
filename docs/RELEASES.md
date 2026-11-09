# Releases

How releases are made and delivered: see `CLAUDE.md`, "How work is delivered".
Deliver them in order; mark a release "delivered" (with the date) once it is in `master`.

| Release | Branch | Tag | Contents | Status |
|---|---|---|---|---|
| 01 | `release/01-foundation` | `delivery-01` | Services shared by API and notebooks; Stage naming replaced by Interpretation; memory database by default (SQLite/BigQuery kept); .env loaded by the app; /ask smoke test; Docker; kct.sh; notebooks 01-06 | prepared |
| 01.1 | `release/01.1-setup-fixes` | `delivery-01.1` | Setup fixes from the first run in ING (Windows laptop): tests skip optional packages that are not installed instead of failing; 01_setup installs httpx with the API group; README section for Windows | prepared |
| 01.2 | `release/01.2-windows-encoding` | `delivery-01.2` | Windows: the setup notebook's commands (pip, tests, API) and the tests read text as UTF-8, so output with characters like ✅ no longer breaks Step 7 | prepared |
| 01.3 | `release/01.3-test-isolation` | `delivery-01.3` | Tests ignore the KCT_* settings of whoever runs them (.env, the setup notebook's Step 1), so a sqlite or gemini setting no longer fails a test | prepared |
| 01.4 | `release/01.4-repository-hygiene` | `delivery-01.4` | .gitignore covers secrets (service-account keys, .env variants), databases and logs anywhere, and documents/archives (C3 evidence); a test fails if any of them, or a notebook with outputs, is committed | prepared |
| 01.5 | `release/01.5-sqlite-check-table` | `delivery-01.5` | 01_setup (Step 6) and kct.sh sqlite use their own table, so 03_sqlite_test no longer fails on an old test_records table; 05/06 show the newest run when no ID is pasted; scripts/run_notebooks.py runs every notebook in order as the check before tagging or pushing | prepared |
| 01.6 | `release/01.6-jupyter-app` | `delivery-01.6` | Clickable app inside Jupyter (KCT_App.ipynb, ipywidgets, no web server or open port): create a case from the control details and test plan, make and browse the test steps; a Next button after each step | prepared |
| 02 | `release/02-evidence-conversion` | `delivery-02` | Evidence made readable for the AI: Word to PDF, Excel to text with coordinates/colors/comments, Outlook emails with threads and attachments; fake evidence factories; notebooks 00 (cleanup), 07-09 | prepared |
| 03 | `release/03-evidence-per-case` | `delivery-03` | Evidence per case: upload API, evidence units (email with its attachments), splitting large files (PDF pages/MB, Excel sheets/rows); notebook 10; app: Evidence tab | prepared |
| 04 | `release/04-assessment` | `delivery-04` | Assessment: one AI call per evidence part, reference checks, combined verdict per test step, background API, run history, read-only PDF report in ING colours with the ING logo slot; notebook 11; app: Assess (live progress) and Result tabs | prepared |
| 05 | `release/05-sharepoint-import` | `delivery-05` | Import a control from SharePoint as a ZIP or synced folder; one AI call picks the one control details file and the one test plan, everything else is evidence; ZIP kept with import.json; notebook 12; app: import in tab 1 | prepared |
| 06 | `release/06-demo` | `delivery-06` | Management demo: DEMO.ipynb, OVERVIEW.md, traceability matrix, executive PDF page, run metrics, record & replay of real AI answers; dashboard in ING style; app: result with KPIs, matrix, trust panel | prepared |
| 07 | `release/07-run-all` | `delivery-07` | App: Run all in one click (test steps, assessment, result) after the import | prepared |
