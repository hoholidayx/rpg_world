from __future__ import annotations

from agent_service.settings import LLMClientSettings
from llm_client.auth import (
    DEFAULT_LLM_SERVICE_TOKEN,
    DEFAULT_LLM_SERVICE_TOKEN_ENV,
)


def test_llm_client_token_uses_shared_default_when_environment_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv(DEFAULT_LLM_SERVICE_TOKEN_ENV, raising=False)

    assert LLMClientSettings().token == DEFAULT_LLM_SERVICE_TOKEN


def test_llm_client_token_prefers_environment_override(monkeypatch) -> None:
    monkeypatch.setenv(DEFAULT_LLM_SERVICE_TOKEN_ENV, "configured-token")

    assert LLMClientSettings().token == "configured-token"
