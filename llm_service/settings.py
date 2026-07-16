"""Process settings for the standalone LLM service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.settings import ProfiledYamlSettings, forgiving_int, optional_bool
from commons.process_logging import (
    ProcessLoggingSettings,
    parse_process_logging_settings,
)
from llm_client.auth import (
    DEFAULT_LLM_SERVICE_TOKEN_ENV,
    resolve_llm_service_token,
    uses_default_llm_service_token,
)

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class LLMServiceListenSettings:
    host: str = "127.0.0.1"
    port: int = 8012
    api_prefix: str = "/llm/v1"
    reload: bool = False


@dataclass(frozen=True)
class LLMServiceAuthSettings:
    token_env: str = DEFAULT_LLM_SERVICE_TOKEN_ENV

    @property
    def token(self) -> str:
        return resolve_llm_service_token(self.token_env)

    @property
    def uses_default_token(self) -> bool:
        return uses_default_llm_service_token(self.token_env)


@dataclass(frozen=True)
class LLMRuntimeSettings:
    llama_max_parallel_models: int = 2
    llama_shutdown_grace_ms: int = 5000


class LLMServiceSettings(ProfiledYamlSettings):
    def __init__(self, profile_name: str | None = None) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "llm_service/settings.yaml"
        super().__init__(profile_name)

    @property
    def service(self) -> LLMServiceListenSettings:
        raw = self._mapping("service")
        return LLMServiceListenSettings(
            host=str(raw.get("host", "127.0.0.1") or "127.0.0.1"),
            port=forgiving_int(raw.get("port", 8012), 8012),
            api_prefix=str(raw.get("api_prefix", "/llm/v1") or "/llm/v1"),
            reload=optional_bool(raw.get("reload", False), False),
        )

    @property
    def auth(self) -> LLMServiceAuthSettings:
        raw = self._mapping("auth")
        return LLMServiceAuthSettings(
            token_env=str(
                raw.get("token_env", DEFAULT_LLM_SERVICE_TOKEN_ENV)
                or DEFAULT_LLM_SERVICE_TOKEN_ENV
            )
        )

    @property
    def runtime(self) -> LLMRuntimeSettings:
        raw = self._mapping("runtime")
        return LLMRuntimeSettings(
            llama_max_parallel_models=max(
                1,
                forgiving_int(raw.get("llama_max_parallel_models", 2), 2),
            ),
            llama_shutdown_grace_ms=max(
                1,
                forgiving_int(raw.get("llama_shutdown_grace_ms", 5000), 5000),
            ),
        )

    @property
    def logging(self) -> ProcessLoggingSettings:
        raw = self._mapping("logging")
        return parse_process_logging_settings(
            raw,
            label="llm_service.logging",
        )


settings = LLMServiceSettings()
