"""API-level settings loaded from dashboard_api/settings.json.

These are distinct from the rpg_core Settings singleton which reads
``settings.yaml``.  API settings control server-level concerns:
port, log level, log file path, etc.
"""

from __future__ import annotations

import json
from pathlib import Path

_API_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"


class ApiSettings:
    """Typed accessor for ``dashboard_api/settings.json``.

    Usage::

        from dashboard_api.settings import api_settings

        port = api_settings.port
        level = api_settings.log_level
        if api_settings.log_chat_messages:
            ...
    """

    def __init__(self) -> None:
        self._raw = self._load()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _load() -> dict:
        if _API_SETTINGS_PATH.is_file():
            with _API_SETTINGS_PATH.open(encoding="utf-8") as f:
                return json.load(f)
        return {}

    def reload(self) -> None:
        """Re-read ``dashboard_api/settings.json`` from disk and update in-memory state."""
        self._raw = self._load()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def port(self) -> int:
        return self._raw.get("port", 8000)

    @property
    def log_level(self) -> str:
        """Python log level name (DEBUG, INFO, WARNING, ERROR)."""
        return self._raw.get("log_level", "INFO")

    @property
    def log_chat_messages(self) -> bool:
        """Log raw user input and assistant output."""
        return self._raw.get("log_chat_messages", True)

    @property
    def log_llm_stats(self) -> bool:
        """Log formatted LLM usage statistics."""
        return self._raw.get("log_llm_stats", True)

    @property
    def log_path(self) -> str | None:
        """Optional file path for chat logs.  ``None`` → stderr only."""
        return self._raw.get("log_path")

    @property
    def api_prefix(self) -> str:
        """API 路由前缀（含版本号，如 ``/dashboard_api/v1``）。"""
        return self._raw.get("api_prefix", "/dashboard_api/v1")


# Singleton
api_settings = ApiSettings()
