# Releases

How releases are made and delivered: see `CLAUDE.md`, "How work is delivered".
Deliver them in order; mark a release "delivered" (with the date) once it is in `master`.

| Release | Branch | Tag | Contents | Status |
|---|---|---|---|---|
| 01 | `release/01-foundation` | `delivery-01` | Services shared by API and notebooks; Stage naming replaced by Interpretation; memory database by default (SQLite/BigQuery kept); .env loaded by the app; /ask smoke test; Docker; kct.sh; notebooks 01-06 | prepared |
| 01.1 | `release/01.1-setup-fixes` | `delivery-01.1` | Setup fixes from the first run in ING (Windows laptop): tests skip optional packages that are not installed instead of failing; 01_setup installs httpx with the API group; README section for Windows | prepared |
| 01.2 | `release/01.2-windows-encoding` | `delivery-01.2` | Windows: the setup notebook's commands (pip, tests, API) and the tests read text as UTF-8, so output with characters like ✅ no longer breaks Step 7 | prepared |
| 01.3 | `release/01.3-test-isolation` | `delivery-01.3` | Tests ignore the KCT_* settings of whoever runs them (.env, the setup notebook's Step 1), so a sqlite or gemini setting no longer fails a test | prepared |
