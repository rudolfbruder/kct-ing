"""Record real model answers once, replay them later (for demos without network or cost).

    KCT_AI_PROVIDER=gemini  KCT_AI_RECORD=demo   every answer is also saved to
                                                 demo/recordings/demo/<agent>/<key>.json
    KCT_AI_PROVIDER=replay  KCT_AI_REPLAY=demo   answers come from those files

A call is found by a key made of the agent, the prompt text and the attachment titles,
so the same input gives the same answer even when files were regenerated (their bytes
differ, their names do not). When no recording matches, the next unused recording of
that agent is taken (and a warning logged), so a slightly different run still plays.
Recordings hold the model's text only, never the documents sent.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set

from services.ai.exceptions import AiConfigurationError
from services.ai.providers.base import ProviderRequest
from services.ai.responses import ProviderResponse, Usage

log = logging.getLogger("kct.ai")


def recording_key(request: ProviderRequest) -> str:
    material = "\n".join([request.agent, request.prompt, *[d.title for d in request.attachments]])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class RecordingProvider:
    """Wraps a real provider and saves every answer."""

    def __init__(self, inner, folder: Path) -> None:
        self.inner = inner
        self.folder = Path(folder)
        self.name = getattr(inner, "name", "provider")

    def prompt(self, request: ProviderRequest) -> ProviderResponse:
        response = self.inner.prompt(request)
        key = recording_key(request)
        target = self.folder / request.agent
        target.mkdir(parents=True, exist_ok=True)
        sequence = len(list(target.glob("*.json"))) + 1
        (target / f"{key[:20]}.json").write_text(json.dumps({
            "agent": request.agent,
            "key": key,
            "sequence": sequence,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": response.model,
            "attachments": [d.title for d in request.attachments],
            "prompt_start": request.prompt[:300],
            "text": response.text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "truncated": response.truncated,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        return response


class ReplayProvider:
    name = "replay"

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        if not self.folder.is_dir():
            raise AiConfigurationError(
                f"No recording at {self.folder}. Record one first: run with a real provider and KCT_AI_RECORD set.")
        self._used: Dict[str, Set[str]] = {}

    def prompt(self, request: ProviderRequest) -> ProviderResponse:
        key = recording_key(request)
        path = self.folder / request.agent / f"{key[:20]}.json"
        if not path.is_file():
            path = self._next_unused(request.agent)
            log.warning("replay: no exact recording for %s, using %s", request.agent, path.name)
        self._used.setdefault(request.agent, set()).add(path.name)
        record = json.loads(path.read_text(encoding="utf-8"))
        return ProviderResponse(
            text=record["text"],
            model=f"{record.get('model', 'recorded')} (replay)",
            usage=Usage(input_tokens=record.get("input_tokens", 0), output_tokens=record.get("output_tokens", 0)),
            truncated=record.get("truncated", False),
        )

    def _next_unused(self, agent: str) -> Path:
        files: List[Path] = sorted(
            (self.folder / agent).glob("*.json"),
            key=lambda p: json.loads(p.read_text(encoding="utf-8")).get("sequence", 0),
        )
        used = self._used.get(agent, set())
        for path in files:
            if path.name not in used:
                return path
        if files:
            return files[-1]
        raise AiConfigurationError(f"The recording {self.folder.name} has no answers for {agent}")
