from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rpg_core.agent import lifecycle as lifecycle_module
from rpg_core.agent.lifecycle import AgentRuntimeLifecycle
from rpg_core.agent.resources import AgentContextResources


class _MemoryManager:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.init_calls = 0
        self.reindex_calls = 0

    def init(self) -> None:
        self.init_calls += 1

    def reindex(self) -> None:
        self.reindex_calls += 1


class _Builder:
    config = SimpleNamespace(enable_lorebook=True, enable_character=True)

    def __init__(self, session_id: str) -> None:
        self.summary_store = f"summary:{session_id}"
        self.story_memory_store = f"story:{session_id}"
        self.batch_summary_store = f"batch:{session_id}"


class _Scene:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    @staticmethod
    def get_tools() -> list:
        return []


class _Manager:
    def __init__(self, value: str) -> None:
        self.value = value

    def list_enabled_entries(self) -> list[dict[str, object]]:
        return [{"name": self.value}]

    def list_enabled_characters(self) -> list[dict[str, object]]:
        return [{"name": self.value}]


class _SubAgent:
    instances: list["_SubAgent"] = []

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.enabled = kwargs.get("enabled", True)
        self.contexts = []
        self.providers = []
        self.__class__.instances.append(self)

    def bind_context(self, context) -> None:  # noqa: ANN001
        self.contexts.append(context)

    def replace_tool_providers(self, providers: list) -> None:
        self.providers = list(providers)

    def get_command_def(self):  # noqa: ANN201
        return None

    def replace_session_stores(self, **kwargs) -> None:  # noqa: ANN003
        self.session_stores = kwargs


class _Compressor:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.kwargs = kwargs

    def replace_session_resources(self, **kwargs) -> None:  # noqa: ANN003
        self.kwargs.update(kwargs)


class _Commands:
    def __init__(self) -> None:
        self.default_calls = 0
        self.providers = []
        self.sub_agents = []

    def register_default_builtins(self) -> None:
        self.default_calls += 1

    def register_command_provider(self, provider) -> None:  # noqa: ANN001
        self.providers.append(provider)

    def replace_command_providers(self, providers: list) -> None:
        self.providers = list(providers)

    def register_sub_agent(self, sub_agent) -> None:  # noqa: ANN001
        self.sub_agents.append(sub_agent)

    def replace_sub_agents(self, sub_agents: list) -> None:
        self.sub_agents = list(sub_agents)


class _ModelRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def provider_for(self, session_id: str):  # noqa: ANN201
        self.calls.append(session_id)
        return object()


class _ToolService:
    def __init__(self) -> None:
        self.refresh_calls = 0

    def refresh_base_registry(self) -> None:
        self.refresh_calls += 1


class _Mailbox:
    def __init__(self) -> None:
        self.start_calls = 0

    def start(self) -> None:
        self.start_calls += 1


def _resources(session_id: str) -> AgentContextResources:
    return AgentContextResources(
        builder=_Builder(session_id),
        character_manager=_Manager(f"character:{session_id}"),
        lorebook_manager=_Manager(f"lore:{session_id}"),
        status_manager=None,
        scene_tracker=_Scene(session_id),
        memory_manager=_MemoryManager(session_id),
    )


@pytest.fixture
def lifecycle_deps(monkeypatch):  # noqa: ANN201
    _SubAgent.instances = []
    monkeypatch.setattr(lifecycle_module, "StatusSubAgent", _SubAgent)
    monkeypatch.setattr(lifecycle_module, "MemorySubAgent", _SubAgent)
    monkeypatch.setattr(lifecycle_module, "SummaryCompressor", _Compressor)
    watcher = SimpleNamespace(start=MagicMock())
    monkeypatch.setattr(lifecycle_module, "get_watcher", lambda: watcher)
    monkeypatch.setattr(
        lifecycle_module,
        "settings",
        SimpleNamespace(
            status_sub_agent_config={"enabled": True},
            memory_sub_agent_config={"enabled": True},
            memory_keep_rounds=4,
            memory_compression_enabled=True,
            memory_compress_batch_size=2,
            rp_module_settings=None,
        ),
    )
    return watcher


@pytest.mark.asyncio
async def test_lifecycle_initialize_is_idempotent(lifecycle_deps) -> None:
    built: list[str] = []

    def factory(*, world_name: str, session_id: str) -> AgentContextResources:
        assert world_name == "World"
        built.append(session_id)
        return _resources(session_id)

    commands = _Commands()
    model = _ModelRuntime()
    tools = _ToolService()
    mailbox = _Mailbox()
    lifecycle = AgentRuntimeLifecycle(
        session_id="s1",
        world_name="World",
        history_enabled=False,
        model_runtime=model,
        command_dispatcher=commands,
        resource_factory=factory,
    )

    await lifecycle.initialize(tool_service=tools, mailbox=mailbox)
    await lifecycle.initialize(tool_service=tools, mailbox=mailbox)

    assert built == ["s1"]
    assert model.calls == ["s1"]
    assert lifecycle.resources.memory_manager.init_calls == 1
    assert commands.default_calls == 1
    assert len(commands.sub_agents) == 2
    assert tools.refresh_calls == 1
    assert mailbox.start_calls == 1
    lifecycle_deps.start.assert_called_once()


@pytest.mark.asyncio
async def test_lifecycle_switch_rebuilds_resources_and_rebinds_subagents(
    lifecycle_deps,
) -> None:
    built: list[str] = []

    def factory(*, world_name: str, session_id: str) -> AgentContextResources:
        del world_name
        built.append(session_id)
        return _resources(session_id)

    lifecycle = AgentRuntimeLifecycle(
        session_id="old",
        world_name="World",
        history_enabled=False,
        model_runtime=_ModelRuntime(),
        command_dispatcher=_Commands(),
        resource_factory=factory,
    )
    tools = _ToolService()
    await lifecycle.initialize(tool_service=tools, mailbox=_Mailbox())
    status_sub_agent = lifecycle.status_sub_agent

    await lifecycle.switch_session("new", tool_service=tools)

    assert lifecycle.session_id == "new"
    assert lifecycle.session_manager.session_id == "new"
    assert built == ["old", "new"]
    assert lifecycle.resources.memory_manager.session_id == "new"
    assert lifecycle.resources.memory_manager.init_calls == 1
    assert status_sub_agent.providers[0].session_id == "new"
    assert len(status_sub_agent.contexts) == 2
    assert tools.refresh_calls == 2
    assert lifecycle_deps.start.call_count == 2


@pytest.mark.asyncio
async def test_lifecycle_can_refresh_sub_agent_bindings_without_rebuilding_resources(
    lifecycle_deps,
) -> None:
    built: list[str] = []

    def factory(*, world_name: str, session_id: str) -> AgentContextResources:
        del world_name
        built.append(session_id)
        return _resources(session_id)

    lifecycle = AgentRuntimeLifecycle(
        session_id="s1",
        world_name="World",
        history_enabled=False,
        model_runtime=_ModelRuntime(),
        command_dispatcher=_Commands(),
        resource_factory=factory,
    )
    await lifecycle.initialize(tool_service=_ToolService(), mailbox=_Mailbox())
    status_sub_agent = lifecycle.status_sub_agent
    memory_sub_agent = lifecycle.memory_sub_agent

    lifecycle.refresh_sub_agent_bindings()

    assert built == ["s1"]
    assert len(status_sub_agent.contexts) == 2
    assert len(memory_sub_agent.contexts) == 2


def test_lifecycle_reindex_memory_uses_typed_resources(lifecycle_deps) -> None:
    lifecycle = AgentRuntimeLifecycle(
        session_id="s1",
        world_name="World",
        history_enabled=False,
        model_runtime=_ModelRuntime(),
        command_dispatcher=_Commands(),
        resource_factory=lambda **_kwargs: _resources("s1"),
    )

    assert lifecycle.reindex_memory() is True
    assert lifecycle.resources.memory_manager.reindex_calls == 1
