from __future__ import annotations

import pytest

import rpg_core.agent.manager as agent_manager_module
from rpg_core.agent.manager import AgentManager
from llm_service.manager import ProviderOverrides


class FakeAgent:
    instances: list["FakeAgent"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.init_calls = 0
        self._session_id = kwargs["session_id"]
        FakeAgent.instances.append(self)

    async def _ensure_initialized(self) -> None:
        self.init_calls += 1


@pytest.fixture(autouse=True)
def _reset_manager(monkeypatch):
    AgentManager.reset()
    monkeypatch.setattr(agent_manager_module, "RPGGameAgent", FakeAgent)
    monkeypatch.setattr(agent_manager_module, "ensure_workspace_dir", lambda *args, **kwargs: None)
    yield
    AgentManager.reset()
    FakeAgent.instances.clear()


def test_get_or_create_reuses_same_key():
    first = AgentManager.get_or_create(workspace="data/test", session_id="s1", api_key="k1")
    second = AgentManager.get_or_create(workspace="data/test", session_id="s1", api_key="k1")

    assert first is second
    assert first.kwargs["workspace"] == "data/test"
    assert first.kwargs["session_id"] == "s1"


def test_get_or_create_separates_by_api_key_and_session():
    first = AgentManager.get_or_create(workspace="data/test", session_id="s1", api_key="k1")
    second = AgentManager.get_or_create(workspace="data/test", session_id="s1", api_key="k2")
    third = AgentManager.get_or_create(workspace="data/test", session_id="s2", api_key="k1")

    assert first is not second
    assert first is not third
    assert len(AgentManager._instances) == 3


def test_get_or_create_passes_api_key_override_to_llm_manager(monkeypatch):
    calls: list[tuple[str, ProviderOverrides | None]] = []

    class FakeProvider:
        def get_default_model(self) -> str:
            return "override-model"

    class FakeLLMManager:
        def get_provider(self, biz_key, overrides=None):  # noqa: ANN001
            calls.append((biz_key, overrides))
            return FakeProvider()

    monkeypatch.setattr(
        agent_manager_module.LLMManager,
        "get",
        classmethod(lambda cls: FakeLLMManager()),
    )

    agent = AgentManager.get_or_create(workspace="data/test", session_id="s1", api_key="header-key")

    assert agent.kwargs["api_key"] == "header-key"
    assert agent.kwargs["model"] == "override-model"
    assert calls[0][0] == "agent.main"
    assert calls[0][1] == ProviderOverrides(openai_api_key="header-key")


@pytest.mark.asyncio
async def test_ensure_initialized_is_keyed_by_workspace_and_session():
    await AgentManager.ensure_initialized(workspace="data/ws1", session_id="s1")
    await AgentManager.ensure_initialized(workspace="data/ws1", session_id="s1")
    await AgentManager.ensure_initialized(workspace="data/ws2", session_id="s1")

    assert len(AgentManager._initialized_targets) == 2
    assert len(FakeAgent.instances) == 2
    assert FakeAgent.instances[0].init_calls == 1
    assert FakeAgent.instances[1].init_calls == 1


def test_reset_clears_cache_and_init_targets():
    AgentManager.get_or_create(workspace="data/test", session_id="s1")
    AgentManager._initialized_targets.add(("data/test", "s1"))

    AgentManager.reset()

    assert AgentManager._instances == {}
    assert AgentManager._initialized_targets == set()
