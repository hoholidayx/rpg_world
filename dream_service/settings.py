from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path

from commons.process_logging import ProcessLoggingSettings, parse_process_logging_settings
from commons.settings import ProfiledYamlSettings, forgiving_int, optional_bool
from llm_client.auth import DEFAULT_LLM_SERVICE_TOKEN_ENV, resolve_llm_service_token
from play_events.auth import DEFAULT_PLAY_EVENT_TOKEN_ENV, resolve_play_event_token

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class DreamServiceListenSettings:
    host: str = "127.0.0.1"
    port: int = 8014
    api_prefix: str = "/dream/v1"
    reload: bool = False


@dataclass(frozen=True)
class DreamClientSettings:
    base_url: str = "http://127.0.0.1:8014/dream/v1"
    request_timeout_ms: int = 60000


@dataclass(frozen=True)
class LLMClientSettings:
    base_url: str
    token_env: str
    request_timeout_ms: int
    stream_timeout_ms: int

    @property
    def token(self) -> str:
        return resolve_llm_service_token(self.token_env)


@dataclass(frozen=True)
class DreamEngineSettings:
    max_map_turns: int = 12
    max_map_chars: int = 24000
    map_concurrency: int = 2
    reduce_candidate_batch_size: int = 32


@dataclass(frozen=True)
class PlayEventPublisherSettings:
    enabled: bool = True
    endpoint_url: str = "http://127.0.0.1:8001/play-api/v1/internal/events"
    token_env: str = DEFAULT_PLAY_EVENT_TOKEN_ENV
    timeout_ms: int = 2000

    @property
    def token(self) -> str:
        return resolve_play_event_token(self.token_env)


class DreamServiceSettings(ProfiledYamlSettings):
    def __init__(self, profile_name: str | None = None) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "dream_service/settings.yaml"
        super().__init__(profile_name)

    @property
    def service(self) -> DreamServiceListenSettings:
        raw = self._mapping("service")
        return DreamServiceListenSettings(
            host=_loopback_host(raw.get("host", "127.0.0.1")),
            port=forgiving_int(raw.get("port", 8014), 8014),
            api_prefix=str(raw.get("api_prefix", "/dream/v1") or "/dream/v1"),
            reload=optional_bool(raw.get("reload", False), False),
        )

    @property
    def dream_client(self) -> DreamClientSettings:
        raw = self._mapping("dream_client")
        return DreamClientSettings(
            base_url=str(
                raw.get("base_url", "http://127.0.0.1:8014/dream/v1")
                or "http://127.0.0.1:8014/dream/v1"
            ).rstrip("/"),
            request_timeout_ms=max(
                1,
                forgiving_int(raw.get("request_timeout_ms", 60000), 60000),
            ),
        )

    @property
    def llm_client(self) -> LLMClientSettings:
        raw = self._mapping("llm_client")
        return LLMClientSettings(
            base_url=str(
                raw.get("base_url", "http://127.0.0.1:8012/llm/v1")
                or "http://127.0.0.1:8012/llm/v1"
            ).rstrip("/"),
            token_env=str(
                raw.get("token_env", DEFAULT_LLM_SERVICE_TOKEN_ENV)
                or DEFAULT_LLM_SERVICE_TOKEN_ENV
            ),
            request_timeout_ms=max(
                1,
                forgiving_int(raw.get("request_timeout_ms", 120000), 120000),
            ),
            stream_timeout_ms=max(
                1,
                forgiving_int(raw.get("stream_timeout_ms", 300000), 300000),
            ),
        )

    @property
    def engine(self) -> DreamEngineSettings:
        raw = self._mapping("engine")
        return DreamEngineSettings(
            max_map_turns=max(
                1,
                forgiving_int(raw.get("max_map_turns", 12), 12),
            ),
            max_map_chars=max(
                1000,
                forgiving_int(raw.get("max_map_chars", 24000), 24000),
            ),
            map_concurrency=max(
                1,
                forgiving_int(raw.get("map_concurrency", 2), 2),
            ),
            reduce_candidate_batch_size=max(
                2,
                forgiving_int(
                    raw.get("reduce_candidate_batch_size", 32),
                    32,
                ),
            ),
        )

    @property
    def play_events(self) -> PlayEventPublisherSettings:
        raw = self._mapping("play_events")
        return PlayEventPublisherSettings(
            enabled=optional_bool(raw.get("enabled", True), True),
            endpoint_url=str(
                raw.get(
                    "endpoint_url",
                    "http://127.0.0.1:8001/play-api/v1/internal/events",
                )
                or "http://127.0.0.1:8001/play-api/v1/internal/events"
            ).rstrip("/"),
            token_env=str(
                raw.get("token_env", DEFAULT_PLAY_EVENT_TOKEN_ENV)
                or DEFAULT_PLAY_EVENT_TOKEN_ENV
            ),
            timeout_ms=max(1, forgiving_int(raw.get("timeout_ms", 2000), 2000)),
        )

    @property
    def logging(self) -> ProcessLoggingSettings:
        return parse_process_logging_settings(
            self._mapping("logging"),
            label="dream_service.logging",
        )


def _loopback_host(value: object) -> str:
    """Keep the unauthenticated v1 service on an explicit loopback bind."""

    host = str(value or "127.0.0.1").strip()
    if host.casefold() == "localhost":
        return "localhost"
    normalized = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise ValueError(
            "dream_service.service.host must be localhost or a loopback IP address"
        ) from exc
    if not address.is_loopback:
        raise ValueError(
            "dream_service.service.host must be localhost or a loopback IP address"
        )
    return normalized


settings = DreamServiceSettings()
