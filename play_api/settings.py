"""Play API process settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.settings import (
    ProfiledYamlSettings,
    forgiving_float,
    forgiving_int,
    optional_bool,
)
from commons.process_logging import (
    ProcessLoggingSettings,
    parse_process_logging_settings,
)
from play_events.auth import DEFAULT_PLAY_EVENT_TOKEN_ENV, resolve_play_event_token

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class PlayApiServiceSettings:
    host: str = "127.0.0.1"
    port: int = 8001
    api_prefix: str = "/play-api/v1"
    reload: bool = False


@dataclass(frozen=True)
class PlayEventStreamSettings:
    token_env: str = DEFAULT_PLAY_EVENT_TOKEN_ENV
    subscriber_queue_capacity: int = 64
    heartbeat_seconds: float = 15.0
    retry_ms: int = 3000

    @property
    def token(self) -> str:
        return resolve_play_event_token(self.token_env)


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
    def events(self) -> PlayEventStreamSettings:
        raw = self._mapping("events")
        return PlayEventStreamSettings(
            token_env=str(
                raw.get("token_env", DEFAULT_PLAY_EVENT_TOKEN_ENV)
                or DEFAULT_PLAY_EVENT_TOKEN_ENV
            ),
            subscriber_queue_capacity=max(
                1,
                forgiving_int(raw.get("subscriber_queue_capacity", 64), 64),
            ),
            heartbeat_seconds=max(
                1.0,
                forgiving_float(raw.get("heartbeat_seconds", 15.0), 15.0),
            ),
            retry_ms=max(100, forgiving_int(raw.get("retry_ms", 3000), 3000)),
        )

    @property
    def logging(self) -> ProcessLoggingSettings:
        raw = self._mapping("logging")
        return parse_process_logging_settings(
            raw,
            label="play_api.logging",
        )


play_settings = PlayApiSettings()
