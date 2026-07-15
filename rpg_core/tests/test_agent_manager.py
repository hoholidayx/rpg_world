from __future__ import annotations

import asyncio

import pytest

import rpg_core.agent.manager as agent_manager_module
from rpg_core.agent.manager import AgentManager
from rpg_core.agent.manager import SessionDeletionInProgressError


class FakeAgent:
    instances: list["FakeAgent"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.init_calls = 0
        self.close_calls = 0
        self._session_id = kwargs["session_id"]
        FakeAgent.instances.append(self)

    async def initialize(self) -> None:
        self.init_calls += 1

    async def close(self) -> None:
        self.close_calls += 1


@pytest.fixture(autouse=True)
async def _reset_manager(monkeypatch):
    await AgentManager.areset()
    monkeypatch.setattr(agent_manager_module, "RPGGameAgent", FakeAgent)
    yield
    await AgentManager.areset()
    FakeAgent.instances.clear()


def test_get_or_create_reuses_same_key():
    first = AgentManager.get_or_create(session_id="s1")
    second = AgentManager.get_or_create(session_id="s1")

    assert first is second
    assert first.kwargs["session_id"] == "s1"


def test_get_or_create_separates_by_session_only():
    first = AgentManager.get_or_create(session_id="s1")
    second = AgentManager.get_or_create(session_id="s1")
    third = AgentManager.get_or_create(session_id="s2")

    assert first is second
    assert first is not third
    assert len(AgentManager._instances) == 2


def test_get_or_create_leaves_main_provider_resolution_to_agent():
    agent = AgentManager.get_or_create(session_id="s1")

    assert agent.kwargs == {"session_id": "s1"}


@pytest.mark.asyncio
async def test_ensure_initialized_is_keyed_by_session_id():
    await AgentManager.ensure_initialized(session_id="s1")
    await AgentManager.ensure_initialized(session_id="s1")
    await AgentManager.ensure_initialized(session_id="s1")

    assert len(AgentManager._initialized_targets) == 1
    assert len(FakeAgent.instances) == 1
    assert FakeAgent.instances[0].init_calls == 1


async def test_reset_clears_cache_and_init_targets():
    AgentManager.get_or_create(session_id="s1")
    AgentManager._initialized_targets.add("s1")

    await AgentManager.areset()

    assert AgentManager._instances == {}
    assert AgentManager._initialized_targets == set()


@pytest.mark.asyncio
async def test_session_deletion_closes_runtime_and_blocks_recreation() -> None:
    agent = AgentManager.get_or_create(session_id="s1")
    AgentManager._initialized_targets.add("s1")

    await AgentManager.begin_session_deletion("s1")

    assert agent.close_calls == 1
    assert "s1" not in AgentManager._instances
    assert "s1" not in AgentManager._initialized_targets
    with pytest.raises(SessionDeletionInProgressError):
        AgentManager.get_or_create(session_id="s1")

    AgentManager.finish_session_deletion("s1")
    replacement = AgentManager.get_or_create(session_id="s1")
    assert replacement is not agent


@pytest.mark.asyncio
async def test_duplicate_session_deletion_is_rejected() -> None:
    await AgentManager.begin_session_deletion("s1")
    try:
        with pytest.raises(SessionDeletionInProgressError):
            await AgentManager.begin_session_deletion("s1")
    finally:
        AgentManager.finish_session_deletion("s1")


@pytest.mark.asyncio
async def test_session_deletion_guard_is_released_when_close_is_cancelled() -> None:
    agent = AgentManager.get_or_create(session_id="s1")

    async def cancel_close() -> None:
        raise asyncio.CancelledError

    agent.close = cancel_close

    with pytest.raises(asyncio.CancelledError):
        await AgentManager.begin_session_deletion("s1")

    assert "s1" not in AgentManager._deleting_sessions
