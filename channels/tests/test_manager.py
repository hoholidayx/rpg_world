"""AgentManager 单例单元测试。

所有测试替换 ``RPGGameAgent``，只验证 ``AgentManager`` 缓存语义，
不触发真实上下文、rpg_data 或 LLM 初始化。
"""

from __future__ import annotations

import pytest

import rpg_core.agent.manager as agent_manager_module
from rpg_core.agent.manager import AgentManager


class FakeAgent:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self._session_id = kwargs["session_id"]
        self.init_calls = 0

    async def initialize(self) -> None:
        self.init_calls += 1

    async def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
async def _fake_agent_runtime(monkeypatch):
    await AgentManager.areset()
    monkeypatch.setattr(agent_manager_module, "RPGGameAgent", FakeAgent)
    yield
    await AgentManager.areset()


class TestAgentManager:
    """AgentManager 核心功能测试。"""

    def test_cache_key(self):
        key1 = AgentManager._cache_key("default")
        key2 = AgentManager._cache_key("mygame")
        assert key1 == "default"
        assert key2 == "mygame"

    def test_get_or_create_default(self):
        agent = AgentManager.get_or_create()
        assert agent._session_id == "default"
        assert agent.kwargs == {"session_id": "default"}
        assert AgentManager._instances["default"] is agent

    def test_get_or_create_twice_returns_same(self):
        a1 = AgentManager.get_or_create(session_id="test1")
        a2 = AgentManager.get_or_create(session_id="test1")
        assert a1 is a2  # 同一实例

    def test_get_or_create_workspace_not_cache_key(self):
        a1 = AgentManager.get_or_create(session_id="test")
        a2 = AgentManager.get_or_create(session_id="test")
        assert a1 is a2

    def test_get_or_create_different_sessions(self):
        a1 = AgentManager.get_or_create(session_id="session1")
        a2 = AgentManager.get_or_create(session_id="session2")
        assert a1 is not a2  # 不同 session 应不同实例

    async def test_reset_clears_instances(self):
        AgentManager.get_or_create()
        assert len(AgentManager._instances) == 1
        await AgentManager.areset()
        assert len(AgentManager._instances) == 0
        assert AgentManager._initialized is False

    async def test_ensure_initialized_once(self):
        await AgentManager.areset()
        assert AgentManager._initialized is False

        await AgentManager.ensure_initialized()
        assert AgentManager._initialized is True
        assert len(AgentManager._instances) == 1

        await AgentManager.ensure_initialized()
        assert len(AgentManager._instances) == 1

    async def test_get_or_create_after_reset(self):
        a1 = AgentManager.get_or_create(session_id="s1")
        await AgentManager.areset()
        a2 = AgentManager.get_or_create(session_id="s1")
        assert a1 is not a2  # reset 后应新创建

    async def test_ensure_initialized_updates_flag(self):
        await AgentManager.areset()
        assert AgentManager._initialized is False
        await AgentManager.ensure_initialized()
        assert AgentManager._initialized is True
