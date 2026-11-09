"""Run every notebook in order: the check before tagging or pushing a release.

    python scripts/run_notebooks.py            all notebooks in order, then those in the project root (DEMO, KCT_App)
    python scripts/run_notebooks.py 04 05      only the notebooks starting with these numbers

Runs in a new temporary storage folder with the fake AI and SQLite: your storage, database and
.env are not used, nothing is sent to an AI and nothing costs money. Notebooks run one after
the other on the same storage, as in a demo (04 makes the data that 05 and 06 show). Outputs are
never written back into the notebooks.

Needs nbclient and ipykernel (pip install nbclient ipykernel). Exit code 1 when a notebook fails.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(prefixes: list) -> int:
    try:
        import nbformat
        from nbclient import NotebookClient
        from nbclient.exceptions import CellExecutionError
    except ImportError:
        print("Needs nbclient and ipykernel: pip install nbclient ipykernel")
        return 2

    notebooks = sorted((ROOT / "notebooks").glob("[0-9][0-9]_*.ipynb"))
    notebooks += sorted(ROOT.glob("*.ipynb"))          # DEMO.ipynb, KCT_App.ipynb
    if prefixes:
        notebooks = [n for n in notebooks if any(n.name.startswith(p) for p in prefixes)]

    storage = Path(tempfile.mkdtemp(prefix="kct-notebooks-"))
    for key in [k for k in os.environ if k.startswith("KCT_")]:
        del os.environ[key]                       # never your own settings
    os.environ.update(KCT_ENV_FILE="", KCT_AI_PROVIDER="fake", KCT_DB_DRIVER="sqlite",
                      KCT_STORAGE_ROOT=str(storage), PYTHONUTF8="1")
    # The notebooks' kernel starts "python": make that the Python running this script (with the packages).
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    print(f"Storage for this run: {storage}\n")

    failed = []
    for path in notebooks:
        notebook = nbformat.read(path, as_version=4)
        started = time.monotonic()
        client = NotebookClient(notebook, timeout=600, kernel_name="python3",
                                resources={"metadata": {"path": str(path.parent)}})
        try:
            client.execute()
            print(f"ok      {path.relative_to(ROOT)}  ({time.monotonic() - started:.0f} s)")
        except CellExecutionError as exc:
            lines = [line for line in str(exc).splitlines() if line.strip()]
            print(f"FAILED  {path.relative_to(ROOT)}\n        {lines[-1] if lines else exc}")
            failed.append(path.name)
        except Exception as exc:  # kernel could not start, timeout, ...
            print(f"FAILED  {path.relative_to(ROOT)}\n        {type(exc).__name__}: {exc}")
            failed.append(path.name)

    print(f"\n{len(notebooks) - len(failed)} of {len(notebooks)} notebooks ran without errors")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
