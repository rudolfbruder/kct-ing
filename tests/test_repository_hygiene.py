"""Guards what gets committed: no secrets, databases, logs, documents, or notebook outputs.

The repository is public and evidence is C3 confidential, so this checks the files git
would commit (the index), not the files on disk: running a notebook without committing
it is fine. Skipped when the project is not a git checkout (e.g. a ZIP download).
"""
from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "key.json", "*-key.json", "*credentials*.json", "*service-account*.json", "*service_account*.json",
    "*.sqlite", "*.sqlite3", "*.db", "*.log",
    "*.zip", "*.pdf", "*.doc", "*.docx", "*.xls", "*.xlsx", "*.xlsm", "*.msg", "*.eml", "*.ppt", "*.pptx",
]
ALLOWED = [".env.example", "tests/fixtures/*"]


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True).stdout


def in_git() -> bool:
    if shutil.which("git") is None:
        return False
    try:
        return git("rev-parse", "--show-toplevel").strip() != ""
    except subprocess.CalledProcessError:
        return False


@unittest.skipUnless(in_git(), "not a git checkout")
class RepositoryHygieneTest(unittest.TestCase):
    def files(self) -> list:
        return [line for line in git("ls-files", "-z").split("\0") if line]

    def test_no_secrets_databases_logs_or_documents_are_committed(self) -> None:
        bad = [f for f in self.files()
               if any(fnmatch.fnmatch(Path(f).name, pattern) for pattern in FORBIDDEN)
               and not any(fnmatch.fnmatch(f, allowed) for allowed in ALLOWED)]
        self.assertEqual(bad, [], "These files must not be in git (secrets, data or documents); "
                                  "remove them with git rm --cached and keep them out of the repo")

    def test_notebooks_are_committed_without_outputs(self) -> None:
        with_outputs = []
        for path in self.files():
            if not path.endswith(".ipynb"):
                continue
            notebook = json.loads(git("show", f":{path}"))      # the version git would commit
            if any(cell.get("outputs") or cell.get("execution_count") for cell in notebook["cells"]):
                with_outputs.append(path)
        self.assertEqual(with_outputs, [], "Clear All Outputs and save before committing these notebooks: "
                                           "outputs can contain real data")


if __name__ == "__main__":
    unittest.main()
