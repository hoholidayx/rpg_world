"""Globally available fixtures for deterministic backend integration tests."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from llm_client.manager import LLMClientManager
from rpg_core import settings as settings_module
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.agent.manager import AgentManager
from rpg_core.utils.watcher import get_watcher
from tests.support.backend import create_integration_session, shutdown_agent
from tests.support.scripted_llm import ScriptedLLMManager


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """Keep only real-provider tests opt-in; deterministic integration is baseline."""

    live_enabled = os.environ.get("LIVE_LLM_TEST") == "1"
    for item in items:
        if "live_llm" in item.keywords and not live_enabled:
            item.add_marker(
                pytest.mark.skip(
                    reason="set LIVE_LLM_TEST=1 to run live LLM tests",
                )
            )


@pytest.fixture
def integration_settings():
    assert settings_module.settings.profile == "test"
    return settings_module.settings


@pytest_asyncio.fixture
async def integration_workspace(tmp_path, monkeypatch):
    from rpg_data.services import reset_data_service_gateways

    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_data.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    watcher = get_watcher()
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(watcher, "stop", lambda: None)
    reset_data_service_gateways()
    await AgentManager.areset()
    yield tmp_path
    await AgentManager.areset()
    reset_data_service_gateways()


@pytest.fixture
def integration_data_gateway(integration_workspace):  # noqa: ARG001
    from rpg_data.services import get_data_service_gateway

    return get_data_service_gateway()


@pytest.fixture
def scripted_llm_manager(monkeypatch) -> ScriptedLLMManager:
    manager = ScriptedLLMManager()
    monkeypatch.setattr(LLMClientManager, "get", classmethod(lambda cls: manager))
    return manager


@pytest_asyncio.fixture
async def integration_agent_factory(
    integration_settings,  # noqa: ARG001
    integration_workspace,
    integration_data_gateway,
    scripted_llm_manager,  # noqa: ARG001
):
    agents: list[RPGGameAgent] = []

    async def factory(
        session_id: str,
        *,
        with_status: bool = False,
        bind_role: bool = True,
        first_message: str = "",
    ) -> RPGGameAgent:
        create_integration_session(
            integration_data_gateway,
            integration_workspace,
            session_id,
            with_status=with_status,
            bind_role=bind_role,
            first_message=first_message,
        )
        agent = RPGGameAgent(session_id=session_id)
        await agent.initialize()
        agents.append(agent)
        return agent

    try:
        yield factory
    finally:
        for agent in agents:
            await shutdown_agent(agent)
        watcher = get_watcher()
        watcher.stop()
        watcher.clear_all()
        await AgentManager.areset()


@pytest_asyncio.fixture
async def integration_agent(integration_agent_factory):
    return await integration_agent_factory("integration_smoke")


@pytest_asyncio.fixture
async def integration_status_agent(integration_agent_factory):
    return await integration_agent_factory("integration_status", with_status=True)
