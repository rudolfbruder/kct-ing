"""Terminal entrypoint, for when you don't want the API running.

    python -m kct.cli cases
    python -m kct.cli files case-001 control_details
    python -m kct.cli summarize case-001 control_details
    python -m kct.cli summarize case-001 test_plan --force
"""
from __future__ import annotations

import argparse
import sys

from . import prompts, storage
from .config import settings
from .models import DocumentKind
from .services import summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kct")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("cases", help="List case folders.")
    sub.add_parser("prompts", help="List prompts and their versions.")

    files_cmd = sub.add_parser("files", help="List source files for a case and kind.")
    files_cmd.add_argument("case_id")
    files_cmd.add_argument("kind", choices=[k.value for k in DocumentKind])

    run_cmd = sub.add_parser("summarize", help="Run stage 1 summarization.")
    run_cmd.add_argument("case_id")
    run_cmd.add_argument("kind", choices=["control_details", "test_plan"])
    run_cmd.add_argument("--prompt-version", default=None)
    run_cmd.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.command == "cases":
            for case_id in storage.list_cases():
                print(case_id)
            return 0

        if args.command == "prompts":
            for name, versions in prompts.available().items():
                print(f"{name}: {', '.join(versions)}")
            return 0

        if args.command == "files":
            for source in storage.source_files(args.case_id, DocumentKind(args.kind)):
                print(
                    f"{source.relative_path}  {source.mime_type}  "
                    f"{source.size_bytes} B  {source.sha256[:12]}"
                )
            return 0

        if args.command == "summarize":
            print(
                f"model={settings.model} location={settings.location} "
                f"temperature={settings.temperature}",
                file=sys.stderr,
            )
            result = summarize.run(
                args.case_id,
                DocumentKind(args.kind),
                prompt_version=args.prompt_version,
                force=args.force,
            )
            print(f"run_id={result.run_id} prompt={result.prompt_version}", file=sys.stderr)
            print(f"written to {result.output_path}", file=sys.stderr)
            print(result.summary)
            return 0

    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
