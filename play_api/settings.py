"""Play API process settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.settings import ProfiledYamlSettings, forgiving_int, optional_bool

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class PlayApiServiceSettings:
    host: str = "127.0.0.1"
    port: int = 8001
    api_prefix: str = "/play-api/v1"
    reload: bool = False


@dataclass(frozen=True)
class PlayApiLoggingSettings:
    log_level: str = "DEBUG"


@dataclass(frozen=True)
class PlayApiBackendSettings:
    mode: str = "agent"
    mock_stream_delay_ms: int = 180


class PlayApiSettings(ProfiledYamlSettings):
    """Typed accessor for Play API process configuration."""

    def __init__(self) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "play_api/settings.yaml"
        super().__init__()

    @property
    def service(self) -> PlayApiServiceSettings:
        raw = self._mapping("service")
        return PlayApiServiceSettings(
            host=str(raw.get("host", "127.0.0.1") or "127.0.0.1"),
            port=forgiving_int(raw.get("port", 8001), 8001),
            api_prefix=str(raw.get("api_prefix", "/play-api/v1") or "/play-api/v1"),
            reload=optional_bool(raw.get("reload", False), False),
        )

    @property
    def logging(self) -> PlayApiLoggingSettings:
        raw = self._mapping("logging")
        return PlayApiLoggingSettings(
            log_level=str(raw.get("log_level", "DEBUG") or "DEBUG"),
        )

    @property
    def backend(self) -> PlayApiBackendSettings:
        raw = self._mapping("backend")
        mode = str(raw.get("mode", "agent") or "agent").lower()
        if mode not in {"agent", "mock"}:
            raise ValueError("play_api backend.mode must be 'agent' or 'mock'")
        return PlayApiBackendSettings(
            mode=mode,
            mock_stream_delay_ms=forgiving_int(raw.get("mock_stream_delay_ms", 180), 180),
        )


play_settings = PlayApiSettings()
