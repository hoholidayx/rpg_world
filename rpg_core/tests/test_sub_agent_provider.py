from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg_world.rpg_core.agent import agent as agent_module
from rpg_world.rpg_core.agent.agent import _resolve_sub_agent_provider
from rpg_world.rpg_core.agent.sub_agents import MemorySubAgent, StatusSubAgent


class DummyProvider:
    def get_default_model(self) -> str:
        return "dummy"


class DummyOpenAIProvider:
    instances: list["DummyOpenAIProvider"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.instances.append(self)

    def get_default_model(self) -> str:
        return str(self.kwargs["model"])


def _patch_settings(monkeypatch, *, llama_process_enabled: bool = True) -> None:
    monkeypatch.setattr(
        agent_module,
        "settings",
        SimpleNamespace(
            memory_settings=SimpleNamespace(llama_process_enabled=llama_process_enabled),
            _as_bool=lambda value, default: value if isinstance(value, bool) else default,
        ),
    )


def test_shared_provider_selection_for_status_and_memory(monkeypatch):
    _patch_settings(monkeypatch)
    shared = DummyProvider()

    provider, provider_config = _resolve_sub_agent_provider(
        name="status_sub_agent",
        cfg={"enabled": True, "llm_provider": "shared", "shared": {}},
        shared_provider=shared,
        main_api_key=None,
        main_base_url=None,
        main_max_tokens=None,
        main_temperature=None,
    )

    status = StatusSubAgent(provider=provider, provider_config=provider_config)
    memory = MemorySubAgent(provider=provider, provider_config=provider_config)

    assert status._get_provider() is shared
    assert memory._get_provider() is shared
    assert memory._provider is shared


def test_openai_provider_selection_for_status_and_memory(monkeypatch):
    _patch_settings(monkeypatch)
    DummyOpenAIProvider.instances = []
    monkeypatch.setattr(
        "rpg_world.rpg_core.agent.openai_provider.OpenAIProvider",
        DummyOpenAIProvider,
    )

    provider, provider_config = _resolve_sub_agent_provider(
        name="memory_sub_agent",
        cfg={
            "enabled": True,
            "llm_provider": "openai",
            "openai": {
                "model": "sub-model",
                "api_key": None,
                "api_key_env": None,
                "base_url": None,
                "max_tokens": None,
                "temperature": None,
            },
        },
        shared_provider=DummyProvider(),
        main_api_key="main-key",
        main_base_url="https://main.example",
        main_max_tokens=123,
        main_temperature=0.4,
    )

    assert provider is None
    status_provider = StatusSubAgent(provider_config=provider_config)._get_provider()
    memory = MemorySubAgent(provider_config=provider_config)
    memory_provider = memory._get_provider()

    assert isinstance(status_provider, DummyOpenAIProvider)
    assert isinstance(memory_provider, DummyOpenAIProvider)
    assert memory._provider is memory_provider
    assert DummyOpenAIProvider.instances[0].kwargs == {
        "model": "sub-model",
        "api_key": "main-key",
        "base_url": "https://main.example",
        "max_tokens": 123,
        "temperature": 0.4,
    }


def test_llama_provider_config_resolves_relative_model_path(tmp_path, monkeypatch):
    _patch_settings(monkeypatch)
    model = tmp_path / "local.gguf"
    model.write_text("fake", encoding="utf-8")

    provider, provider_config = _resolve_sub_agent_provider(
        name="status_sub_agent",
        cfg={
            "enabled": True,
            "llm_provider": "llama",
            "llama": {
                "model_path": str(model),
                "n_ctx": 4096,
                "n_gpu_layers": 2,
                "request_timeout_ms": 7000,
                "max_tokens": 128,
                "temperature": 0.2,
            },
        },
        shared_provider=DummyProvider(),
        main_api_key=None,
        main_base_url=None,
        main_max_tokens=None,
        main_temperature=None,
    )

    assert provider is None
    assert provider_config.mode == "llama"
    assert provider_config.llama["model_path"] == str(model.resolve())
    assert provider_config.llama["n_ctx"] == 4096


def test_invalid_llm_provider_is_rejected(monkeypatch):
    _patch_settings(monkeypatch)

    with pytest.raises(ValueError, match="llm_provider"):
        _resolve_sub_agent_provider(
            name="status_sub_agent",
            cfg={"enabled": True, "llm_provider": "anthropic"},
            shared_provider=DummyProvider(),
            main_api_key=None,
            main_base_url=None,
            main_max_tokens=None,
            main_temperature=None,
        )


def test_openai_model_is_required(monkeypatch):
    _patch_settings(monkeypatch)

    with pytest.raises(ValueError, match="openai.model"):
        _resolve_sub_agent_provider(
            name="memory_sub_agent",
            cfg={"enabled": True, "llm_provider": "openai", "openai": {"model": None}},
            shared_provider=DummyProvider(),
            main_api_key=None,
            main_base_url=None,
            main_max_tokens=None,
            main_temperature=None,
        )


def test_llama_model_path_is_required(monkeypatch):
    _patch_settings(monkeypatch)

    with pytest.raises(ValueError, match="llama.model_path"):
        _resolve_sub_agent_provider(
            name="status_sub_agent",
            cfg={"enabled": True, "llm_provider": "llama", "llama": {"model_path": None}},
            shared_provider=DummyProvider(),
            main_api_key=None,
            main_base_url=None,
            main_max_tokens=None,
            main_temperature=None,
        )


def test_disabled_sub_agent_does_not_validate_unused_provider_blocks(monkeypatch):
    _patch_settings(monkeypatch)

    provider, provider_config = _resolve_sub_agent_provider(
        name="memory_sub_agent",
        cfg={
            "enabled": False,
            "llm_provider": "broken",
            "openai": {"model": None},
            "llama": {"model_path": "/definitely/missing.gguf"},
        },
        shared_provider=None,
        main_api_key=None,
        main_base_url=None,
        main_max_tokens=None,
        main_temperature=None,
    )

    assert provider is None
    assert provider_config.mode == "shared"

    memory = MemorySubAgent(provider_config=provider_config, enabled=False)
    assert memory.get_command_def() is None
    assert memory.accept_command("/compact") is False
    assert memory.accept_command("/extract_story_memory") is False


def test_llama_provider_requires_enabled_llama_process(monkeypatch, tmp_path):
    _patch_settings(monkeypatch, llama_process_enabled=False)
    model = tmp_path / "local.gguf"
    model.write_text("fake", encoding="utf-8")

    with pytest.raises(ValueError, match="llama_process_enabled"):
        _resolve_sub_agent_provider(
            name="memory_sub_agent",
            cfg={"enabled": True, "llm_provider": "llama", "llama": {"model_path": str(model)}},
            shared_provider=DummyProvider(),
            main_api_key=None,
            main_base_url=None,
            main_max_tokens=None,
            main_temperature=None,
        )
