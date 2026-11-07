#!/usr/bin/env bash
# All commands to set up and run KCT without Docker (Vertex AI Workbench in ING,
# or any machine with Python 3.9+). Run from anywhere; it works in the project folder.
#
#   ./kct.sh install            packages for the notebooks (Gemini), only what is missing
#   ./kct.sh install --api      also the API packages (fastapi, uvicorn, python-multipart)
#   ./kct.sh install --claude   also Claude (anthropic[vertex])
#   ./kct.sh check              what is installed and which settings are active
#   ./kct.sh ask ["question"]   smoke test: ask the AI "What is 5+2?" through AskService
#   ./kct.sh api [port]         start the API (default port 8000)
#   ./kct.sh curl [port]        call /health and /ask on a running API
#   ./kct.sh steps [id]         list case interpretations, or print one
#   ./kct.sh sqlite             check SQLite works: write and read records in a test file
#   ./kct.sh test               run the test suite (fake AI, temporary storage)
#
# Settings: put them in .env (copy .env.example); this script loads it.
# Without .env, KCT_AI_PROVIDER defaults to fake here, so nothing reaches the cloud.
# Internal pip mirror: export KCT_PIP_INDEX=<mirror-url> before "install".
set -euo pipefail

cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"

if [[ -f .env ]]; then
  set -a; source .env; set +a
fi
export KCT_AI_PROVIDER="${KCT_AI_PROVIDER:-fake}"

# Python import name, pip requirement
NOTEBOOK_PACKAGES=("pydantic:pydantic>=2" "google.genai:google-genai" "pandas:pandas" "docx:python-docx" "reportlab:reportlab" "openpyxl:openpyxl" "extract_msg:extract-msg" "pypdf:pypdf")
API_PACKAGES=("fastapi:fastapi" "uvicorn:uvicorn" "multipart:python-multipart" "httpx:httpx")
CLAUDE_PACKAGES=("anthropic:anthropic[vertex]")

has_module() {
  "$PYTHON" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$1') else 1)" 2>/dev/null
}

pydantic_major() {
  "$PYTHON" -c "import pydantic; print(pydantic.VERSION.split('.')[0])" 2>/dev/null || echo 0
}

check_python() {
  if ! command -v "$PYTHON" >/dev/null; then
    echo "No $PYTHON found. Install Python 3.9+ or set PYTHON=/path/to/python." >&2
    exit 1
  fi
  "$PYTHON" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" || {
    echo "Python 3.9+ needed, found $("$PYTHON" --version)." >&2
    exit 1
  }
}

cmd_install() {
  check_python
  local wanted=("${NOTEBOOK_PACKAGES[@]}")
  for arg in "$@"; do
    case "$arg" in
      --api) wanted+=("${API_PACKAGES[@]}") ;;
      --claude) wanted+=("${CLAUDE_PACKAGES[@]}") ;;
      *) echo "Unknown option $arg (use --api, --claude)" >&2; exit 1 ;;
    esac
  done

  local missing=()
  for entry in "${wanted[@]}"; do
    local module="${entry%%:*}" requirement="${entry#*:}"
    if [[ "$module" == "pydantic" ]] && has_module pydantic && [[ "$(pydantic_major)" -lt 2 ]]; then
      echo "pydantic 1.x found; KCT needs 2.x"
      missing+=("$requirement")
    elif has_module "$module"; then
      echo "ok       $requirement"
    else
      echo "missing  $requirement"
      missing+=("$requirement")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    echo "Nothing to install."
    return
  fi

  local pip_args=(install)
  # Inside a virtualenv --user is not allowed and not needed.
  if ! "$PYTHON" -c "import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)"; then
    pip_args+=(--user)
  fi
  if [[ -n "${KCT_PIP_INDEX:-}" ]]; then
    pip_args+=(--index-url "$KCT_PIP_INDEX")
  fi

  echo "Installing: ${missing[*]}"
  "$PYTHON" -m pip "${pip_args[@]}" "${missing[@]}"
  echo "Done. Restart any open notebook kernel to pick up the new packages."
}

cmd_check() {
  check_python
  echo "Python:   $("$PYTHON" --version) ($(command -v "$PYTHON"))"
  echo "sqlite3:  $("$PYTHON" -c 'import sqlite3; print(sqlite3.sqlite_version)') (built into Python)"
  for entry in "${NOTEBOOK_PACKAGES[@]}" "${API_PACKAGES[@]}" "${CLAUDE_PACKAGES[@]}"; do
    local module="${entry%%:*}" requirement="${entry#*:}"
    if has_module "$module"; then echo "ok       $requirement"; else echo "missing  $requirement"; fi
  done
  echo
  echo "KCT_AI_PROVIDER=${KCT_AI_PROVIDER}"
  echo "KCT_AI_MODEL=${KCT_AI_MODEL:-<default>}"
  echo "KCT_PROJECT_ID=${KCT_PROJECT_ID:-<not set>}"
  echo "KCT_FILES_DRIVER=${KCT_FILES_DRIVER:-local}"
  echo "KCT_DB_DRIVER=${KCT_DB_DRIVER:-memory}"
  [[ -f .env ]] && echo "(.env loaded)" || echo "(no .env; copy .env.example to .env to configure)"
}

cmd_ask() {
  check_python
  local question="${1:-What is 5+2?}"
  KCT_QUESTION="$question" "$PYTHON" -c '
import os
from services.app import boot
result = boot().ask.ask(os.environ["KCT_QUESTION"])
print(result.answer)
print(f"({result.provider}/{result.model}, {result.input_tokens} in / {result.output_tokens} out tokens, {result.duration_ms} ms)")
'
}

cmd_api() {
  check_python
  local port="${1:-${KCT_API_PORT:-8000}}"
  echo "API on http://localhost:$port (docs: /docs). On a workbench: https://<workbench-url>/proxy/$port/docs"
  exec "$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port "$port"
}

cmd_curl() {
  # Python instead of curl, so it works where curl is not installed.
  check_python
  local port="${1:-${KCT_API_PORT:-8000}}"
  KCT_URL="http://localhost:$port/api/v1" "$PYTHON" -c '
import json, os, urllib.request
base = os.environ["KCT_URL"]
print(urllib.request.urlopen(base + "/health", timeout=10).read().decode())
request = urllib.request.Request(
    base + "/ask",
    data=json.dumps({"question": "What is 5+2?"}).encode(),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(request, timeout=300).read().decode())
'
}

cmd_steps() {
  check_python
  "$PYTHON" scripts/test_steps.py "$@"
}

cmd_sqlite() {
  # Same check as notebooks/03_sqlite_test.ipynb, from the terminal.
  check_python
  "$PYTHON" -c '
import sqlite3
from pathlib import Path
db = Path("storage/sqlite_test.sqlite")
db.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(db) as con:
    con.execute("CREATE TABLE IF NOT EXISTS setup_check (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    con.execute("INSERT INTO setup_check (name) VALUES (?)", ("written by kct.sh sqlite",))
    rows = con.execute("SELECT id, name, created_at FROM setup_check ORDER BY id DESC LIMIT 5").fetchall()
print("SQLite", sqlite3.sqlite_version, "works; file", db)
for row in rows:
    print(*row, sep="  ")
'
}

cmd_test() {
  check_python
  "$PYTHON" -m unittest discover tests
}

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
}

command="${1:-help}"
shift || true
case "$command" in
  install) cmd_install "$@" ;;
  check) cmd_check ;;
  ask) cmd_ask "$@" ;;
  api) cmd_api "$@" ;;
  curl) cmd_curl "$@" ;;
  steps) cmd_steps "$@" ;;
  sqlite) cmd_sqlite ;;
  test) cmd_test ;;
  help|-h|--help) usage ;;
  *) echo "Unknown command $command" >&2; usage; exit 1 ;;
esac
