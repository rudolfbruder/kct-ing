"""Versioned prompt loading.

Prompts live on disk as <name>.v<N>.md and are never built by string
concatenation in code. The version that ran is recorded in every run record, so
a verdict can always be traced back to the exact wording that produced it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .config import settings

VERSION_RE = re.compile(r"^(?P<name>.+)\.v(?P<version>\d+)\.md$")


class PromptNotFound(Exception):
    pass


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str
    sha256: str
    path: Path


def _candidates(name: str) -> dict[int, Path]:
    root = settings.prompts_root
    if not root.is_dir():
        raise PromptNotFound(f"Prompts folder not found: {root}")
    found: dict[int, Path] = {}
    for path in root.glob(f"{name}.v*.md"):
        match = VERSION_RE.match(path.name)
        if match and match.group("name") == name:
            found[int(match.group("version"))] = path
    if not found:
        raise PromptNotFound(f"No prompt files matching {name}.v*.md in {root}")
    return found


def load(name: str, version: str | None = None) -> Prompt:
    """Load a prompt by name. Without a version, the highest on disk wins."""
    found = _candidates(name)
    if version is None:
        number = max(found)
    else:
        number = int(str(version).lstrip("vV"))
        if number not in found:
            raise PromptNotFound(
                f"Prompt {name} v{number} not found. Available: "
                + ", ".join(f"v{n}" for n in sorted(found))
            )
    path = found[number]
    text = path.read_text(encoding="utf-8")
    return Prompt(
        name=name,
        version=f"v{number}",
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        path=path,
    )


def available() -> dict[str, list[str]]:
    root = settings.prompts_root
    out: dict[str, list[str]] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.v*.md")):
        match = VERSION_RE.match(path.name)
        if match:
            out.setdefault(match.group("name"), []).append(f"v{match.group('version')}")
    return out
