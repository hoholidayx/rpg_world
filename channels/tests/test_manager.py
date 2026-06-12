"""AgentManager 单例单元测试。

所有测试 mock 掉 ``RPGGameAgent._ensure_initialized`` 避免真实 LLM 调用，
无需 API key。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from rpg_world.rpg_core.agent.manager import AgentManager

# mock agent._ensure_initialized 为 no-op，避免创建真实的 OpenAI provider
_AGENT_PATCH_PATH = "rpg_world.rpg_core.agent.agent.RPGGameAgent._ensure_initialized"


class TestAgentManager:
    """AgentManager 核心功能测试。"""

    def setup_method(self) -> None:
        AgentManager.reset()

    def test_cache_key(self):
        key1 = AgentManager._cache_key("data/test", "default", None)
        key2 = AgentManager._cache_key("data/test", "default", "sk-xxx")
        key3 = AgentManager._cache_key("data/test", "mygame", None)
        assert key1 == "data/test::default::"
        assert key2 == "data/test::default::sk-xxx"
        assert key3 == "data/test::mygame::"

    def test_get_or_create_default(self):
        agent = AgentManager.get_or_create(workspace="data/test")
        assert agent._session_id == "default"
        assert AgentManager._instances["data/test::default::"] is agent

    def test_get_or_create_twice_returns_same(self):
        a1 = AgentManager.get_or_create(workspace="data/test", session_id="test1", api_key="key1")
        a2 = AgentManager.get_or_create(workspace="data/test", session_id="test1", api_key="key1")
        assert a1 is a2  # 同一实例

    def test_get_or_create_different_keys(self):
        a1 = AgentManager.get_or_create(workspace="data/test", session_id="test", api_key="key1")
        a2 = AgentManager.get_or_create(workspace="data/test", session_id="test", api_key="key2")
        assert a1 is not a2  # 不同 api_key 应不同实例

    def test_get_or_create_different_sessions(self):
        a1 = AgentManager.get_or_create(workspace="data/test", session_id="session1")
        a2 = AgentManager.get_or_create(workspace="data/test", session_id="session2")
        assert a1 is not a2  # 不同 session 应不同实例

    def test_reset_clears_instances(self):
        AgentManager.get_or_create(workspace="data/test")
        assert len(AgentManager._instances) == 1
        AgentManager.reset()
        assert len(AgentManager._instances) == 0
        assert AgentManager._initialized is False

    def test_ensure_initialized_once(self):
        with patch(_AGENT_PATCH_PATH, return_value=None):
            AgentManager.reset()
            assert AgentManager._initialized is False

            import asyncio
            asyncio.run(AgentManager.ensure_initialized(workspace="data/test"))
            assert AgentManager._initialized is True
            assert len(AgentManager._instances) == 1

            asyncio.run(AgentManager.ensure_initialized(workspace="data/test"))
            assert len(AgentManager._instances) == 1

    def test_get_or_create_after_reset(self):
        a1 = AgentManager.get_or_create(workspace="data/test", session_id="s1")
        AgentManager.reset()
        a2 = AgentManager.get_or_create(workspace="data/test", session_id="s1")
        assert a1 is not a2  # reset 后应新创建

    async def test_ensure_initialized_updates_flag(self):
        with patch(_AGENT_PATCH_PATH, return_value=None):
            AgentManager.reset()
            assert AgentManager._initialized is False
            await AgentManager.ensure_initialized(workspace="data/test")
            assert AgentManager._initialized is True
