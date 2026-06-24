"""Agent service process settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.settings import ProfiledYamlSettings, forgiving_int, optional_bool

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class ServiceSettings:
    host: str = "127.0.0.1"
    port: int = 8010
    api_prefix: str = "/agent/v1"
    reload: bool = False


@dataclass(frozen=True)
class AgentClientSettings:
    base_url: str = "http://127.0.0.1:8010/agent/v1"
    request_timeout_ms: int = 60000
    stream_timeout_ms: int = 300000


@dataclass(frozen=True)
class AgentServiceLoggingSettings:
    log_level: str = "DEBUG"


class AgentServiceSettings(ProfiledYamlSettings):
    """Typed accessor for Agent service process configuration."""

    def __init__(self) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "agent_service/settings.yaml"
        super().__init__()

    @property
    def service(self) -> ServiceSettings:
        raw = self._mapping("service")
        return ServiceSettings(
            host=str(raw.get("host", "127.0.0.1") or "127.0.0.1"),
            port=forgiving_int(raw.get("port", 8010), 8010),
            api_prefix=str(raw.get("api_prefix", "/agent/v1") or "/agent/v1"),
            reload=optional_bool(raw.get("reload", False), False),
        )

    @property
    def agent_client(self) -> AgentClientSettings:
        raw = self._mapping("agent_client")
        return AgentClientSettings(
            base_url=str(raw.get("base_url", "http://127.0.0.1:8010/agent/v1") or "http://127.0.0.1:8010/agent/v1").rstrip("/"),
            request_timeout_ms=forgiving_int(raw.get("request_timeout_ms", 60000), 60000),
            stream_timeout_ms=forgiving_int(raw.get("stream_timeout_ms", 300000), 300000),
        )

    @property
    def logging(self) -> AgentServiceLoggingSettings:
        raw = self._mapping("logging")
        return AgentServiceLoggingSettings(
            log_level=str(raw.get("log_level", "DEBUG") or "DEBUG"),
        )


settings = AgentServiceSettings()
