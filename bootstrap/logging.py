"""Log setup.

    storage/logs/app.log      what the app did (cases stored, steps generated, errors)
    storage/logs/agents.log   one JSON line per agent call: provider, model, tokens, time, full output
"""
from __future__ import annotations

import logging

from services.config import Settings

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(config: Settings) -> None:
    config.logs_dir.mkdir(parents=True, exist_ok=True)

    app = logging.getLogger("kct")
    if app.handlers:  # already configured (reload, tests)
        return
    app.setLevel(logging.INFO)

    app_file = logging.FileHandler(config.logs_dir / "app.log", encoding="utf-8")
    app_file.setFormatter(logging.Formatter(FORMAT))
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT))
    app.addHandler(app_file)
    app.addHandler(console)

    # Full agent calls go to agents.log only, as bare JSON lines. Agents also
    # write a one-line summary to "kct", which lands in app.log.
    agents = logging.getLogger("kct.ai.calls")
    agents.setLevel(logging.INFO)
    agents.propagate = False
    agents_file = logging.FileHandler(config.logs_dir / "agents.log", encoding="utf-8")
    agents_file.setFormatter(logging.Formatter("%(message)s"))
    agents.addHandler(agents_file)
