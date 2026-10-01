"""Central logging configuration (Phase 8.2 — production-readiness audit found zero
logging anywhere in the app: DB failures, auth events, and AI-provider failures were
all completely invisible). Configures the root logger once at startup; every module
gets its own logger via `logging.getLogger(__name__)` and inherits this setup.

Logs go to stdout only (12-factor style) — this app doesn't manage log files itself;
a container runtime or process manager is expected to capture/ship stdout. Never log
secrets (passwords, tokens, API keys) — call sites are responsible for that, this
module only sets format/level.
"""
from __future__ import annotations

import logging
import sys

from app.config import settings


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
        force=True,  # override any prior basicConfig call (e.g. from uvicorn/pytest)
    )
