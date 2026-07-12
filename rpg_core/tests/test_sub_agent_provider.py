from __future__ import annotations

import pytest

from llm_service import manager as manager_module
from rpg_core.agent.sub_agents import MemorySubAgent, StatusSubAgent


class DummyProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    def get_default_model(self) -> str:
        return self.name


def test_shared_provider_selection_is_hidden_behind_biz_key(monkeypatch):
    shared = DummyProvider("shared")
    calls: list[str] = []

    class FakeManager:
        def get_provider(self, biz_key):  # noqa: ANN001
            calls.append(biz_key)
            return shared

    monkeypatch.setattr(manager_module.LLMManager, "get", classmethod(lambda cls: FakeManager()))

    status = StatusSubAgent(provider_biz_key="agent.status_sub_agent", enabled=True)
    memory = MemorySubAgent(provider_biz_key="agent.memory_sub_agent", enabled=True)

    assert status._get_provider() is shared
    assert memory._get_provider() is shared
    assert calls == ["agent.status_sub_agent", "agent.memory_sub_agent"]


def test_biz_key_routes_to_distinct_providers(monkeypatch):
    providers = {
        "agent.status_sub_agent": DummyProvider("status"),
        "agent.memory_sub_agent": DummyProvider("memory"),
    }

    class FakeManager:
        def get_provider(self, biz_key):  # noqa: ANN001
            return providers[biz_key]

    monkeypatch.setattr(manager_module.LLMManager, "get", classmethod(lambda cls: FakeManager()))

    assert StatusSubAgent(provider_biz_key="agent.status_sub_agent")._get_provider() is providers["agent.status_sub_agent"]
    assert MemorySubAgent(provider_biz_key="agent.memory_sub_agent")._get_provider() is providers["agent.memory_sub_agent"]


def test_disabled_sub_agent_does_not_trigger_provider_resolution(monkeypatch):
    class FakeManager:
        def get_provider(self, biz_key):  # noqa: ANN001
            raise AssertionError(f"provider should not be resolved for {biz_key}")

    monkeypatch.setattr(manager_module.LLMManager, "get", classmethod(lambda cls: FakeManager()))

    memory = MemorySubAgent(provider_biz_key="agent.memory_sub_agent", enabled=False)
    assert memory.get_command_def() is None
    assert memory.accept_command("/compact") is False
    assert memory.accept_command("/extract_story_memory") is False


def test_provider_biz_key_is_required():
    with pytest.raises(ValueError, match="provider_biz_key is required"):
        StatusSubAgent(provider_biz_key=" ")
