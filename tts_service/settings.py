from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.process_logging import ProcessLoggingSettings, parse_process_logging_settings
from commons.settings import ProfiledYamlSettings, forgiving_int, optional_bool
from llm_client.auth import DEFAULT_LLM_SERVICE_TOKEN_ENV, resolve_llm_service_token

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class TTSServiceListenSettings:
    host: str = "127.0.0.1"
    port: int = 8013
    api_prefix: str = "/tts/v1"
    reload: bool = False


@dataclass(frozen=True)
class TTSClientSettings:
    base_url: str = "http://127.0.0.1:8013/tts/v1"
    request_timeout_ms: int = 60000


@dataclass(frozen=True)
class TTSWorkerSettings:
    concurrency: int = 1


@dataclass(frozen=True)
class LLMClientSettings:
    base_url: str
    token_env: str
    request_timeout_ms: int
    stream_timeout_ms: int

    @property
    def token(self) -> str:
        return resolve_llm_service_token(self.token_env)


class TTSServiceSettings(ProfiledYamlSettings):
    def __init__(self, profile_name: str | None = None) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "tts_service/settings.yaml"
        super().__init__(profile_name)

    @property
    def service(self) -> TTSServiceListenSettings:
        raw = self._mapping("service")
        return TTSServiceListenSettings(
            host=str(raw.get("host", "127.0.0.1") or "127.0.0.1"),
            port=forgiving_int(raw.get("port", 8013), 8013),
            api_prefix=str(raw.get("api_prefix", "/tts/v1") or "/tts/v1"),
            reload=optional_bool(raw.get("reload", False), False),
        )

    @property
    def tts_client(self) -> TTSClientSettings:
        raw = self._mapping("tts_client")
        return TTSClientSettings(
            base_url=str(
                raw.get("base_url", "http://127.0.0.1:8013/tts/v1")
                or "http://127.0.0.1:8013/tts/v1"
            ).rstrip("/"),
            request_timeout_ms=forgiving_int(
                raw.get("request_timeout_ms", 60000),
                60000,
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
            request_timeout_ms=forgiving_int(
                raw.get("request_timeout_ms", 120000),
                120000,
            ),
            stream_timeout_ms=forgiving_int(
                raw.get("stream_timeout_ms", 300000),
                300000,
            ),
        )

    @property
    def worker(self) -> TTSWorkerSettings:
        raw = self._mapping("worker")
        return TTSWorkerSettings(max(1, forgiving_int(raw.get("concurrency", 1), 1)))

    @property
    def logging(self) -> ProcessLoggingSettings:
        return parse_process_logging_settings(
            self._mapping("logging"),
            label="tts_service.logging",
        )


settings = TTSServiceSettings()
