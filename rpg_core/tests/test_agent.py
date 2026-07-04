from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import rpg_core.agent.agent as agent_module
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.agent.command import CommandDispatcher
from rpg_core.agent.tools import BaseTool
from rpg_core.context.rpg_context import HotHistoryLayer, Message, RPGContext, Role
from rpg_core.session.manager import SessionManager
from rpg_core.session.turn_metadata import InvalidTurnMetadataError
from llm_service.manager import ProviderOverrides
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.settings import RPModuleSettings
from rpg_core.agent.agent_types import (
    AgentStreamEvent,
    QueueItem,
    QueueKind,
    StreamEventKind,
    _StreamSentinel,
)


@pytest.mark.asyncio
async def test_queue_consumer_surfaces_stream_errors(monkeypatch):
    agent = object.__new__(RPGGameAgent)
    agent._queue = asyncio.Queue()
    agent._cmd_dispatcher = None
    agent._send_impl = AsyncMock()
    agent._send_stream_impl = AsyncMock(side_effect=RuntimeError("boom"))

    future = asyncio.get_running_loop().create_future()
    event_queue: asyncio.Queue = asyncio.Queue()
    await agent._queue.put(
        QueueItem(
            kind=QueueKind.SEND_STREAM,
            user_input="hello",
            future=future,
            event_queue=event_queue,
        )
    )

    consumer_task = asyncio.create_task(agent._queue_consumer())
    try:
        first = await asyncio.wait_for(event_queue.get(), timeout=1)
        second = await asyncio.wait_for(event_queue.get(), timeout=1)

        assert isinstance(first, AgentStreamEvent)
        assert first.kind == StreamEventKind.ERROR
        assert first.content == "boom"
        assert isinstance(second, _StreamSentinel)
        assert future.done()
        assert future.result() is None
    finally:
        consumer_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer_task


@pytest.mark.asyncio
async def test_queue_consumer_serializes_truncate_after_send() -> None:
    agent = object.__new__(RPGGameAgent)
    agent._queue = asyncio.Queue()
    agent._cmd_dispatcher = None
    order: list[str] = []
    release_send = asyncio.Event()

    async def send_impl(_text: str) -> AgentReply:
        order.append("send-start")
        await release_send.wait()
        order.append("send-end")
        return AgentReply(text="ok")

    def truncate_impl(turn_id: int) -> dict[str, object]:
        order.append(f"truncate-{turn_id}")
        return {"status": "truncated", "turn_id": turn_id, "removed": 1}

    agent._send_impl = send_impl
    agent._send_stream_impl = AsyncMock()
    agent._truncate_history_from_turn_impl = truncate_impl

    send_future = asyncio.get_running_loop().create_future()
    truncate_future = asyncio.get_running_loop().create_future()
    await agent._queue.put(QueueItem(kind=QueueKind.SEND, user_input="go", future=send_future))
    await agent._queue.put(
        QueueItem(
            kind=QueueKind.TRUNCATE_HISTORY,
            user_input="",
            future=truncate_future,
            turn_id=2,
        )
    )

    consumer_task = asyncio.create_task(agent._queue_consumer())
    try:
        while order != ["send-start"]:
            await asyncio.sleep(0)
        assert not truncate_future.done()

        release_send.set()
        await asyncio.wait_for(truncate_future, timeout=1)

        assert order == ["send-start", "send-end", "truncate-2"]
        assert truncate_future.result()["status"] == "truncated"
    finally:
        consumer_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer_task


@pytest.mark.asyncio
async def test_send_impl_rejects_invalid_loaded_turn_metadata_before_new_turn():
    session = SessionManager(history_enabled=False)
    session.replace_history(
        [
            Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
            Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=0),
        ],
        persist=False,
    )
    agent = object.__new__(RPGGameAgent)
    agent._cmd_dispatcher = None
    agent._session = session

    with pytest.raises(InvalidTurnMetadataError, match=r"history\[1\]"):
        await agent._send_impl("go")


def test_compose_stored_user_input_places_user_text_after_scene_close_tag() -> None:
    scene_ctx = "[scene]\n位置: 北境森林\n[/scene]"

    assert RPGGameAgent._compose_stored_user_input(scene_ctx, "我观察四周") == (
        "[scene]\n位置: 北境森林\n[/scene]\n我观察四周"
    )


@pytest.mark.asyncio
async def test_ensure_initialized_is_idempotent(monkeypatch):
    class FakeFixedLayerComposer:
        def __init__(self, _world_name: str) -> None:
            self.sections = []

    class FakeSubAgent:
        def __init__(self, *args, **kwargs) -> None:
            self.enabled = kwargs.get("enabled", True)
            self.add_tool_provider = MagicMock()
            self.bind_context = MagicMock()

    class FakeCompressor:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    class FakeCommandDispatcher:
        def __init__(self, agent) -> None:
            self.agent = agent
            self.register_default_builtins = MagicMock()
            self.register_sub_agent = MagicMock()

    class FakeWatcher:
        def __init__(self) -> None:
            self.start = MagicMock()

    fake_watcher = FakeWatcher()
    def fake_create_task(coro):
        coro.close()
        return MagicMock()

    class FakeManager:
        def get_provider(self, biz_key):  # noqa: ANN001
            return object()

    monkeypatch.setattr(agent_module, "FixedLayerComposer", FakeFixedLayerComposer)
    monkeypatch.setattr(agent_module, "StatusSubAgent", FakeSubAgent)
    monkeypatch.setattr(agent_module, "MemorySubAgent", FakeSubAgent)
    monkeypatch.setattr(agent_module, "SummaryCompressor", FakeCompressor)
    monkeypatch.setattr(agent_module, "CommandDispatcher", FakeCommandDispatcher)
    monkeypatch.setattr(agent_module, "get_watcher", lambda: fake_watcher)
    monkeypatch.setattr(agent_module.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(agent_module.LLMManager, "get", classmethod(lambda cls: FakeManager()))
    monkeypatch.setattr(
        agent_module,
        "settings",
        SimpleNamespace(
            status_sub_agent_config={"enabled": False},
            memory_sub_agent_config={"enabled": False},
            memory_keep_rounds=5,
            memory_compression_enabled=False,
            memory_compress_batch_size=2,
        ),
    )

    agent = object.__new__(RPGGameAgent)
    agent._initialized = False
    agent._init_lock = None
    agent._world_name = "world"
    agent._session_id = "s1"
    agent._model = "gpt-4o"
    agent._api_key = None
    agent._base_url = None
    agent._max_tokens = None
    agent._temperature = None
    agent._session = SimpleNamespace(load=MagicMock())
    agent._memory_manager = None
    agent._builder = SimpleNamespace(
        _summary_store=None,
        _story_memory=None,
        _batch_summary_store=None,
    )
    agent._character_mgr = None
    agent._lorebook_mgr = None
    agent._status_mgr = None
    agent._scene_tracker = None
    agent._provider = None
    agent._status_sub_agent = None
    agent._memory_sub_agent = None
    agent._compressor = None
    agent._cmd_dispatcher = None
    agent._setup_tool_registry = MagicMock()
    agent._queue = asyncio.Queue()
    agent._consumer_task = None
    agent._extra_tools = []
    agent._rpg_ctx = {}

    await agent._ensure_initialized()
    await agent._ensure_initialized()

    agent._session.load.assert_called_once()
    agent._setup_tool_registry.assert_called_once()
    fake_watcher.start.assert_called_once()
    assert agent._consumer_task is not None
    assert agent._initialized is True


@pytest.mark.asyncio
async def test_switch_session_reinitializes_memory_and_starts_watcher(monkeypatch):
    class FakeWatcher:
        def __init__(self) -> None:
            self.start = MagicMock()

    fake_watcher = FakeWatcher()
    monkeypatch.setattr(agent_module, "get_watcher", lambda: fake_watcher)

    agent = object.__new__(RPGGameAgent)
    agent._initialized = True
    agent._session_id = "old"
    agent._refresh_rpg_context = MagicMock()
    agent._memory_manager = SimpleNamespace(init=MagicMock())
    agent._session = SimpleNamespace(switch_to=MagicMock())
    agent._setup_tool_registry = MagicMock()

    await agent.switch_session("new")

    agent._refresh_rpg_context.assert_called_once()
    agent._memory_manager.init.assert_called_once()
    fake_watcher.start.assert_called_once()
    agent._session.switch_to.assert_called_once_with("new")
    agent._setup_tool_registry.assert_called_once()


def test_rpg_game_agent_default_model_no_longer_forces_gpt4o(monkeypatch):
    monkeypatch.setattr(agent_module.RPGGameAgent, "_refresh_rpg_context", lambda self: None)

    agent = RPGGameAgent(
        session_id="test",
        model=None,
    )

    assert agent._model is None
    assert agent._provider_overrides == ProviderOverrides()


def test_setup_rp_module_registry_adds_dice_fixed_section():
    agent = object.__new__(RPGGameAgent)
    agent._session_id = "s1"
    agent._world_name = "world"
    agent._status_mgr = None
    agent._scene_tracker = None

    agent._setup_rp_module_registry()

    assert agent._rp_module_registry is not None
    assert any(section.id == "rp_module_dice" for section in agent._fixed_sections)


def test_register_rp_module_commands_exposes_check_dc():
    agent = object.__new__(RPGGameAgent)
    agent._cmd_dispatcher = CommandDispatcher(agent=agent)
    agent._rp_module_registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(),
    )

    agent._register_rp_module_commands()

    command_names = [command.name for command in agent._cmd_dispatcher.list_commands()]
    assert "/roll" in command_names
    assert "/check_dc" in command_names
    assert "/check" not in command_names


@pytest.mark.asyncio
async def test_get_context_json_does_not_mutate_history(fake_token_counter):
    class FakeBuilder:
        config = SimpleNamespace(hot_history_rounds=2)

        def __init__(self) -> None:
            self.last_messages = None

        def build(self, *, messages, **_kwargs):  # noqa: ANN001
            self.last_messages = messages
            return RPGContext(hot_history=HotHistoryLayer(messages=list(messages)))

    history = [Message(Role.USER, "old", turn_id=1, seq_in_turn=1)]
    builder = FakeBuilder()
    agent = object.__new__(RPGGameAgent)
    agent._ensure_initialized = AsyncMock()
    agent._session_id = "s_json"
    agent._token_counter = fake_token_counter
    agent._builder = builder
    agent._fixed_sections = []
    agent._session = SimpleNamespace(history=history)
    agent._character_mgr = None
    agent._lorebook_mgr = None
    agent._status_mgr = None
    agent._scene_tracker = None
    agent._rp_module_registry = None

    payload = json.loads(await agent.get_context_json("preview"))

    assert [message.content for message in history] == ["old"]
    assert builder.last_messages is not history
    assert [message.content for message in builder.last_messages] == ["old", "preview"]
    assert payload["sessionId"] == "s_json"
    assert payload["messages"] == [
        {"role": "user", "content": "old", "turn_id": 1, "seq_in_turn": 1},
        {"role": "user", "content": "preview"},
    ]


def test_setup_tool_registry_registers_rp_module_tools(tmp_path, monkeypatch):
    class FakeTool(BaseTool):
        name = "rp_fake_tool"
        description = "fake"

        def parameters(self):
            return {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            return "ok"

    class FakeRegistry:
        def get_tools(self):
            return [FakeTool()]

    class FakeGateway:
        catalog = SimpleNamespace(get_session_runtime_dir=lambda session_id: tmp_path)

    import rpg_data.services as data_services

    monkeypatch.setattr(data_services, "get_data_service_gateway", lambda: FakeGateway())

    agent = object.__new__(RPGGameAgent)
    agent._session_id = "s1"
    agent._scene_tracker = None
    agent._extra_tools = []
    agent._rp_module_registry = FakeRegistry()

    agent._setup_tool_registry()

    assert "rp_fake_tool" in agent._tool_registry


@pytest.mark.asyncio
async def test_ensure_initialized_populates_model_from_provider(monkeypatch):
    class FakeFixedLayerComposer:
        def __init__(self, _world_name: str) -> None:
            self.sections = []

    class FakeSubAgent:
        def __init__(self, *args, **kwargs) -> None:
            self.enabled = kwargs.get("enabled", True)
            self.add_tool_provider = MagicMock()
            self.bind_context = MagicMock()

    class FakeCompressor:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeCommandDispatcher:
        def __init__(self, *args, **kwargs) -> None:
            self.register_default_builtins = MagicMock()
            self.register_sub_agent = MagicMock()

    class FakeWatcher:
        def __init__(self) -> None:
            self.start = MagicMock()

    class FakeProvider:
        def get_default_model(self) -> str:
            return "provider-model"

    class FakeManager:
        def get_provider(self, _biz_key):  # noqa: ANN001
            return FakeProvider()

    fake_watcher = FakeWatcher()
    def fake_create_task(coro):
        coro.close()
        return MagicMock()

    monkeypatch.setattr(agent_module, "FixedLayerComposer", FakeFixedLayerComposer)
    monkeypatch.setattr(agent_module, "StatusSubAgent", FakeSubAgent)
    monkeypatch.setattr(agent_module, "MemorySubAgent", FakeSubAgent)
    monkeypatch.setattr(agent_module, "SummaryCompressor", FakeCompressor)
    monkeypatch.setattr(agent_module, "CommandDispatcher", FakeCommandDispatcher)
    monkeypatch.setattr(agent_module, "get_watcher", lambda: fake_watcher)
    monkeypatch.setattr(agent_module.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(agent_module.LLMManager, "get", classmethod(lambda cls: FakeManager()))
    monkeypatch.setattr(
        agent_module,
        "settings",
        SimpleNamespace(
            status_sub_agent_config={"enabled": False},
            memory_sub_agent_config={"enabled": False},
            memory_keep_rounds=5,
            memory_compression_enabled=False,
            memory_compress_batch_size=2,
        ),
    )

    agent = object.__new__(RPGGameAgent)
    agent._initialized = False
    agent._init_lock = None
    agent._world_name = "world"
    agent._session_id = "s1"
    agent._model = None
    agent._api_key = None
    agent._base_url = None
    agent._max_tokens = None
    agent._temperature = None
    agent._session = SimpleNamespace(load=MagicMock())
    agent._memory_manager = None
    agent._builder = SimpleNamespace(
        _summary_store=None,
        _story_memory=None,
        _batch_summary_store=None,
    )
    agent._character_mgr = None
    agent._lorebook_mgr = None
    agent._status_mgr = None
    agent._scene_tracker = None
    agent._provider = None
    agent._status_sub_agent = None
    agent._memory_sub_agent = None
    agent._compressor = None
    agent._cmd_dispatcher = None
    agent._setup_tool_registry = MagicMock()
    agent._queue = asyncio.Queue()
    agent._consumer_task = None
    agent._extra_tools = []
    agent._rpg_ctx = {}

    await agent._ensure_initialized()

    assert agent._model == "provider-model"
