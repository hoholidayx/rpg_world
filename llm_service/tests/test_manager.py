from __future__ import annotations

from types import SimpleNamespace

from llm_service.manager import LLMManager
from llm_service.openai_provider import OpenAIProvider


class _DummyAsyncOpenAI:
    instances: list["_DummyAsyncOpenAI"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.instances.append(self)


def _openai_cfg(provider_key: str, *, max_tokens: int | None = None):
    return SimpleNamespace(
        provider_key=provider_key,
        provider="openai",
        kind="chat",
        openai_model="test-model",
        openai_api_key="test-key",
        openai_base_url="https://llm.example",
        openai_max_tokens=max_tokens,
        openai_temperature=0.2,
    )


def test_shared_provider_key_reuses_raw_client_but_not_biz_provider(monkeypatch) -> None:
    configs = {
        "agent.main": _openai_cfg("shared_chat", max_tokens=512),
        "agent.status_sub_agent": _openai_cfg("shared_chat", max_tokens=128),
    }
    _DummyAsyncOpenAI.instances.clear()
    monkeypatch.setattr("llm_service.manager.AsyncOpenAI", _DummyAsyncOpenAI)
    monkeypatch.setattr("llm_service.manager.resolve_biz_config", configs.__getitem__)

    manager = LLMManager()
    main = manager.get_provider("agent.main")
    status = manager.get_provider("agent.status_sub_agent")

    assert isinstance(main, OpenAIProvider)
    assert isinstance(status, OpenAIProvider)
    assert main is not status
    assert main._client is status._client
    assert main._max_tokens == 512
    assert status._max_tokens == 128
    assert len(_DummyAsyncOpenAI.instances) == 1
    assert manager.get_provider("agent.main") is main


def test_provider_key_selection_is_cached_independently(monkeypatch) -> None:
    configs = {
        "chat_a": _openai_cfg("chat_a", max_tokens=256),
        "chat_b": _openai_cfg("chat_b", max_tokens=512),
    }

    def resolve(_biz_key: str, *, provider_key: str | None = None):  # noqa: ANN202
        return configs[provider_key or "chat_a"]

    _DummyAsyncOpenAI.instances.clear()
    monkeypatch.setattr("llm_service.manager.AsyncOpenAI", _DummyAsyncOpenAI)
    monkeypatch.setattr("llm_service.manager.resolve_biz_config", resolve)
    manager = LLMManager()

    first = manager.get_provider("agent.main", provider_key="chat_a")
    second = manager.get_provider("agent.main", provider_key="chat_b")
    assert manager.get_provider("agent.main", provider_key="chat_a") is first
    assert first is not second
    assert len(_DummyAsyncOpenAI.instances) == 2
