"""Typed media-service process and client settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.settings import ProfiledYamlSettings, forgiving_int, optional_bool
from llm_client.auth import (
    DEFAULT_LLM_SERVICE_TOKEN_ENV,
    resolve_llm_service_token,
)

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class MediaServiceListenSettings:
    host: str = "127.0.0.1"
    port: int = 8011
    api_prefix: str = "/media/v1"
    reload: bool = False


@dataclass(frozen=True)
class MediaClientSettings:
    base_url: str = "http://127.0.0.1:8011/media/v1"
    request_timeout_ms: int = 60000


@dataclass(frozen=True)
class MediaWorkerSettings:
    concurrency: int = 1


@dataclass(frozen=True)
class MediaBackgroundWorkerSettings:
    concurrency: int = 1


@dataclass(frozen=True)
class LLMClientSettings:
    base_url: str = "http://127.0.0.1:8012/llm/v1"
    token_env: str = DEFAULT_LLM_SERVICE_TOKEN_ENV
    request_timeout_ms: int = 60000
    stream_timeout_ms: int = 300000

    @property
    def token(self) -> str:
        return resolve_llm_service_token(self.token_env)


@dataclass(frozen=True)
class MediaServiceLoggingSettings:
    log_level: str = "DEBUG"


class MediaServiceSettings(ProfiledYamlSettings):
    def __init__(self, profile_name: str | None = None) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "media_service/settings.yaml"
        super().__init__(profile_name)

    @property
    def service(self) -> MediaServiceListenSettings:
        raw = self._mapping("service")
        return MediaServiceListenSettings(
            host=str(raw.get("host", "127.0.0.1") or "127.0.0.1"),
            port=forgiving_int(raw.get("port", 8011), 8011),
            api_prefix=str(raw.get("api_prefix", "/media/v1") or "/media/v1"),
            reload=optional_bool(raw.get("reload", False), False),
        )

    @property
    def media_client(self) -> MediaClientSettings:
        raw = self._mapping("media_client")
        return MediaClientSettings(
            base_url=str(
                raw.get("base_url", "http://127.0.0.1:8011/media/v1")
                or "http://127.0.0.1:8011/media/v1"
            ).rstrip("/"),
            request_timeout_ms=forgiving_int(
                raw.get("request_timeout_ms", 60000),
                60000,
            ),
        )

    @property
    def worker(self) -> MediaWorkerSettings:
        raw = self._mapping("worker")
        return MediaWorkerSettings(
            concurrency=max(1, forgiving_int(raw.get("concurrency", 1), 1)),
        )

    @property
    def background_worker(self) -> MediaBackgroundWorkerSettings:
        raw = self._mapping("background_worker")
        return MediaBackgroundWorkerSettings(
            concurrency=max(1, forgiving_int(raw.get("concurrency", 1), 1)),
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
            request_timeout_ms=forgiving_int(
                raw.get("request_timeout_ms", 60000),
                60000,
            ),
            stream_timeout_ms=forgiving_int(
                raw.get("stream_timeout_ms", 300000),
                300000,
            ),
        )

    @property
    def logging(self) -> MediaServiceLoggingSettings:
        raw = self._mapping("logging")
        return MediaServiceLoggingSettings(
            log_level=str(raw.get("log_level", "DEBUG") or "DEBUG"),
        )


settings = MediaServiceSettings()
