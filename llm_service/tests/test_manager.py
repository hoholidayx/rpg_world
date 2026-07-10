from __future__ import annotations

from types import SimpleNamespace

from llm_service.llama_provider import LlamaCompletionProvider
from llm_service.manager import LLMManager, ProviderOverrides
from llm_service.openai_provider import OpenAIProvider


class _DummyAsyncOpenAI:
    instances: list[_DummyAsyncOpenAI] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.instances.append(self)


def _openai_cfg(
    provider_key: str,
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        provider_key=provider_key,
        provider="openai",
        kind="chat",
        openai_model="test-model",
        openai_api_key="test-key",
        openai_base_url="https://llm.example",
        openai_max_tokens=max_tokens,
        openai_temperature=temperature,
    )


def _llama_cfg(provider_key: str, *, max_tokens: int = 512) -> SimpleNamespace:
    return SimpleNamespace(
        provider_key=provider_key,
        provider="llama",
        kind="chat",
        llama_model_path="/tmp/chat.gguf",
        llama_n_ctx=2048,
        llama_n_gpu_layers=0,
        llama_request_timeout_ms=60000,
        llama_max_tokens=max_tokens,
        llama_temperature=0.0,
    )


def test_openai_biz_with_shared_provider_key_reuses_client(monkeypatch) -> None:
    configs = {
        "agent.main": _openai_cfg("shared_chat", max_tokens=512, temperature=0.2),
        "agent.status_sub_agent": _openai_cfg("shared_chat", max_tokens=128, temperature=0.0),
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


def test_openai_different_provider_keys_do_not_share_client(monkeypatch) -> None:
    configs = {
        "agent.main": _openai_cfg("chat_a"),
        "agent.status_sub_agent": _openai_cfg("chat_b"),
    }
    _DummyAsyncOpenAI.instances.clear()
    monkeypatch.setattr("llm_service.manager.AsyncOpenAI", _DummyAsyncOpenAI)
    monkeypatch.setattr("llm_service.manager.resolve_biz_config", configs.__getitem__)

    manager = LLMManager()
    first = manager.get_provider("agent.main")
    second = manager.get_provider("agent.status_sub_agent")

    assert first._client is not second._client
    assert len(_DummyAsyncOpenAI.instances) == 2


def test_llama_biz_with_shared_provider_key_reuses_model(monkeypatch) -> None:
    created: list[object] = []

    class FakeLlamaCompletionModel:
        def __init__(self, model_path: str, **kwargs) -> None:
            self.model_path = model_path
            self.kwargs = kwargs
            created.append(self)

    configs = {
        "agent.main": _llama_cfg("shared_llama", max_tokens=512),
        "agent.status_sub_agent": _llama_cfg("shared_llama", max_tokens=128),
    }
    monkeypatch.setattr("llm_service.manager.LlamaCompletionModel", FakeLlamaCompletionModel)
    monkeypatch.setattr("llm_service.manager.resolve_biz_config", configs.__getitem__)

    manager = LLMManager()
    main = manager.get_provider("agent.main")
    status = manager.get_provider("agent.status_sub_agent")

    assert isinstance(main, LlamaCompletionProvider)
    assert isinstance(status, LlamaCompletionProvider)
    assert main is not status
    assert main._model is status._model
    assert main._max_tokens == 512
    assert status._max_tokens == 128
    assert len(created) == 1


def test_provider_overrides_keep_provider_instances_isolated(monkeypatch) -> None:
    _DummyAsyncOpenAI.instances.clear()
    monkeypatch.setattr("llm_service.manager.AsyncOpenAI", _DummyAsyncOpenAI)
    monkeypatch.setattr(
        "llm_service.manager.resolve_biz_config",
        lambda _biz_key: _openai_cfg("shared_chat", max_tokens=256),
    )

    manager = LLMManager()
    base = manager.get_provider("agent.main")
    overridden = manager.get_provider(
        "agent.main",
        overrides=ProviderOverrides(openai_max_tokens=1024, openai_temperature=0.8),
    )

    assert base is not overridden
    assert base._client is overridden._client
    assert base._max_tokens == 256
    assert overridden._max_tokens == 1024
    assert overridden._temperature == 0.8


def test_switching_provider_key_reuses_cached_provider_when_switching_back(monkeypatch) -> None:
    configs = {
        "chat_a": _openai_cfg("chat_a", max_tokens=256),
        "chat_b": _openai_cfg("chat_b", max_tokens=512),
    }
    resolved_keys: list[str] = []

    def resolve(_biz_key: str, *, provider_key: str | None = None):  # noqa: ANN202
        selected = provider_key or "chat_a"
        resolved_keys.append(selected)
        return configs[selected]

    _DummyAsyncOpenAI.instances.clear()
    monkeypatch.setattr("llm_service.manager.AsyncOpenAI", _DummyAsyncOpenAI)
    monkeypatch.setattr("llm_service.manager.resolve_biz_config", resolve)

    manager = LLMManager()
    first = manager.get_provider("agent.main", provider_key="chat_a")
    second = manager.get_provider("agent.main", provider_key="chat_b")
    switched_back = manager.get_provider("agent.main", provider_key="chat_a")

    assert first is switched_back
    assert first is not second
    assert first._client is not second._client
    assert first._max_tokens == 256
    assert second._max_tokens == 512
    assert resolved_keys == ["chat_a", "chat_b", "chat_a"]
    assert len(_DummyAsyncOpenAI.instances) == 2
