"""Dashboard API process settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.settings import ProfiledYamlSettings, forgiving_int, optional_bool

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class DashboardApiServiceSettings:
    host: str = "127.0.0.1"
    port: int = 8000
    api_prefix: str = "/dashboard_api/v1"
    reload: bool = False


@dataclass(frozen=True)
class DashboardApiLoggingSettings:
    log_level: str = "DEBUG"
    watcher_log_level: str = "DEBUG"
    manager_log_level: str = "DEBUG"
    log_chat_messages: bool = True
    log_llm_stats: bool = True
    log_path: str | None = None


class ApiSettings(ProfiledYamlSettings):
    """Typed accessor for Dashboard API process configuration."""

    def __init__(self) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "dashboard_api/settings.yaml"
        super().__init__()

    def reload(self) -> None:
        """Re-read process YAML settings."""
        super().__init__()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def service(self) -> DashboardApiServiceSettings:
        raw = self._mapping("service")
        return DashboardApiServiceSettings(
            host=str(raw.get("host", "127.0.0.1") or "127.0.0.1"),
            port=forgiving_int(raw.get("port", 8000), 8000),
            api_prefix=str(raw.get("api_prefix", "/dashboard_api/v1") or "/dashboard_api/v1"),
            reload=optional_bool(raw.get("reload", False), False),
        )

    @property
    def logging(self) -> DashboardApiLoggingSettings:
        raw = self._mapping("logging")
        log_path = raw.get("log_path")
        return DashboardApiLoggingSettings(
            log_level=str(raw.get("log_level", "DEBUG") or "DEBUG"),
            watcher_log_level=str(raw.get("watcher_log_level", raw.get("log_level", "DEBUG")) or "DEBUG"),
            manager_log_level=str(raw.get("manager_log_level", raw.get("log_level", "DEBUG")) or "DEBUG"),
            log_chat_messages=optional_bool(raw.get("log_chat_messages", True), True),
            log_llm_stats=optional_bool(raw.get("log_llm_stats", True), True),
            log_path=str(log_path) if log_path else None,
        )

    @property
    def port(self) -> int:
        return self.service.port

    @property
    def log_level(self) -> str:
        """Python log level name (DEBUG, INFO, WARNING, ERROR)."""
        return self.logging.log_level

    @property
    def log_chat_messages(self) -> bool:
        """Log raw user input and assistant output."""
        return self.logging.log_chat_messages

    @property
    def log_llm_stats(self) -> bool:
        """Log formatted LLM usage statistics."""
        return self.logging.log_llm_stats

    @property
    def log_path(self) -> str | None:
        """Optional file path for chat logs.  ``None`` → stderr only."""
        return self.logging.log_path

    @property
    def api_prefix(self) -> str:
        """API 路由前缀（含版本号，如 ``/dashboard_api/v1``）。"""
        return self.service.api_prefix


# Singleton
api_settings = ApiSettings()
