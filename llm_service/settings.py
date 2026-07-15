"""Process settings for the standalone LLM service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from commons.settings import ProfiledYamlSettings, forgiving_int, optional_bool

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class LLMServiceListenSettings:
    host: str = "127.0.0.1"
    port: int = 8012
    api_prefix: str = "/llm/v1"
    reload: bool = False


@dataclass(frozen=True)
class LLMServiceAuthSettings:
    token_env: str = "RPG_WORLD_LLM_SERVICE_TOKEN"

    def require_token(self) -> str:
        token = (os.environ.get(self.token_env) or "").strip()
        if not token:
            raise ValueError(f"LLM service auth token is required in environment variable {self.token_env}")
        return token


@dataclass(frozen=True)
class LLMRuntimeSettings:
    llama_max_parallel_models: int = 2


@dataclass(frozen=True)
class LLMServiceLoggingSettings:
    log_level: str = "DEBUG"


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
            token_env=str(raw.get("token_env", "RPG_WORLD_LLM_SERVICE_TOKEN") or "RPG_WORLD_LLM_SERVICE_TOKEN")
        )

    @property
    def runtime(self) -> LLMRuntimeSettings:
        raw = self._mapping("runtime")
        return LLMRuntimeSettings(
            llama_max_parallel_models=max(
                1,
                forgiving_int(raw.get("llama_max_parallel_models", 2), 2),
            )
        )

    @property
    def logging(self) -> LLMServiceLoggingSettings:
        raw = self._mapping("logging")
        return LLMServiceLoggingSettings(
            log_level=str(raw.get("log_level", "DEBUG") or "DEBUG")
        )


settings = LLMServiceSettings()
