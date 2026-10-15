"""Print the test steps of one case interpretation, with its metadata on top.

Terminal (from the project folder):

    python scripts/test_steps.py              list all case interpretations
    python scripts/test_steps.py 3            test steps of case interpretation 3
    python scripts/test_steps.py 3 --json     metadata and test steps as JSON

Jupyter notebook (kernel started in the project folder):

    %run scripts/test_steps.py 3

    from scripts.test_steps import show, table
    show(3)        # printed like the terminal
    table(3)       # pandas DataFrame, one row per test step

Reads through the database repository, so it follows KCT_DB_DRIVER and
KCT_DB_PATH the same way the API does.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.control_testing.data import CaseInterpretation  # noqa: E402
from services.database import manager  # noqa: E402
from services.database.exceptions import RecordNotFoundError  # noqa: E402

WIDTH = 100


def load(case_interpretation_id: str) -> CaseInterpretation:
    return manager.repository().find_interpretation(case_interpretation_id)


def render(interpretation: CaseInterpretation) -> str:
    meta = interpretation.metadata
    lines = [
        "=" * WIDTH,
        f"Case interpretation {meta.case_interpretation_id}",
        f"  case_id:     {meta.case_id} ({meta.case_reference})",
        f"  provider:    {meta.provider}",
        f"  model:       {meta.model}",
        f"  created_at:  {meta.created_at}",
        f"  test steps:  {meta.step_count}",
        "=" * WIDTH,
    ]
    for step in interpretation.test_steps:
        lines += [
            "",
            f"Test step {step.id}  [{step.status}]  {step.reference}: {step.title}",
            *_wrap(step.description, "    "),
            "  Acceptance criteria:",
            *[line for c in step.acceptance_criteria for line in _wrap(c, "    - ", "      ")],
            "  Refusal criteria:",
            *[line for c in step.refusal_criteria for line in _wrap(c, "    - ", "      ")],
        ]
    return "\n".join(lines)


def show(case_interpretation_id: str) -> None:
    print(render(load(case_interpretation_id)))


def table(case_interpretation_id: str):
    """One row per test step, metadata repeated on every row. Needs pandas."""
    import pandas as pd

    interpretation = load(case_interpretation_id)
    meta = interpretation.metadata
    return pd.DataFrame(
        [
            {
                "case_interpretation_id": meta.case_interpretation_id,
                "case_id": meta.case_id,
                "case_reference": meta.case_reference,
                **step.model_dump(exclude={"case_interpretation_id", "case_id"}),
            }
            for step in interpretation.test_steps
        ]
    ).set_index("id")


def list_interpretations() -> str:
    rows = manager.repository().interpretations()
    if not rows:
        return "No case interpretations yet. Run POST /api/v1/test-steps first."
    header = f"{'case_interpretation_id':<36}  {'case':<9}  {'steps':>5}  {'provider/model':<28}  created_at"
    return "\n".join(
        [header, "-" * len(header)]
        + [
            f"{m.case_interpretation_id:<36}  {m.case_reference:<9}  {m.step_count:>5}  "
            f"{m.provider + '/' + m.model:<28}  {m.created_at[:19]}"
            for m in rows
        ]
    )


def _wrap(text: str, first: str, rest: str = "") -> list:
    return textwrap.wrap(text, WIDTH, initial_indent=first, subsequent_indent=rest or first)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Print the test steps of a case interpretation.")
    parser.add_argument("case_interpretation_id", nargs="?")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)

    try:
        if args.case_interpretation_id is None:
            print(list_interpretations())
        elif args.json:
            print(load(args.case_interpretation_id).model_dump_json(indent=2, exclude={"summaries"}))
        else:
            show(args.case_interpretation_id)
    except RecordNotFoundError as exc:
        print(exc, file=sys.stderr)


if __name__ == "__main__":
    main()
