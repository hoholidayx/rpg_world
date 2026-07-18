from __future__ import annotations

from agent_service.settings import LLMClientSettings, PlayEventPublisherSettings
from llm_client.auth import (
    DEFAULT_LLM_SERVICE_TOKEN,
    DEFAULT_LLM_SERVICE_TOKEN_ENV,
)
from play_events.auth import (
    DEFAULT_PLAY_EVENT_TOKEN,
    DEFAULT_PLAY_EVENT_TOKEN_ENV,
)


def test_llm_client_token_uses_shared_default_when_environment_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv(DEFAULT_LLM_SERVICE_TOKEN_ENV, raising=False)

    assert LLMClientSettings().token == DEFAULT_LLM_SERVICE_TOKEN


def test_llm_client_token_prefers_environment_override(monkeypatch) -> None:
    monkeypatch.setenv(DEFAULT_LLM_SERVICE_TOKEN_ENV, "configured-token")

    assert LLMClientSettings().token == "configured-token"


def test_play_event_publisher_token_uses_shared_resolution(monkeypatch) -> None:
    monkeypatch.delenv(DEFAULT_PLAY_EVENT_TOKEN_ENV, raising=False)
    assert PlayEventPublisherSettings().token == DEFAULT_PLAY_EVENT_TOKEN

    monkeypatch.setenv(DEFAULT_PLAY_EVENT_TOKEN_ENV, "event-token")
    assert PlayEventPublisherSettings().token == "event-token"
