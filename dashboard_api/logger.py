"""API logging configuration loaded from dashboard_api/settings.yaml.

Usage::

    from dashboard_api.logger import chat_logger

    chat_logger.info("USER [%s]: %s", session_id, message)
    chat_logger.error("STREAM ERROR [%s]: %s", session_id, exc)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dashboard_api.settings import api_settings

# ── Resolve config ──────────────────────────────────────────────────────

_log_level_name = api_settings.log_level.upper()
_log_level = getattr(logging, _log_level_name, logging.DEBUG)

# ── Chat logger ─────────────────────────────────────────────────────────

chat_logger = logging.getLogger("rpg_api.chat")
chat_logger.setLevel(_log_level)

if not chat_logger.handlers:
    # Stream handler (stderr)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(_log_level)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    chat_logger.addHandler(handler)

    # Optional file handler
    log_path = api_settings.log_path
    if log_path:
        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(_log_level)
        file_handler.setFormatter(formatter)
        chat_logger.addHandler(file_handler)
