"""API-level settings loaded from api/settings.json.

These are distinct from the rpg_core Settings singleton which reads
``rpg_world/settings.json``.  API settings control server-level concerns:
port, log level, log file path, etc.
"""

from __future__ import annotations

import json
from pathlib import Path

_API_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"


class ApiSettings:
    """Typed accessor for ``api/settings.json``.

    Usage::

        from rpg_world.api.settings import api_settings

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
        """Re-read ``api/settings.json`` from disk and update in-memory state."""
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


# Singleton
api_settings = ApiSettings()
