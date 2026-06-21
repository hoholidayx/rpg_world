from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import rpg_world.rpg_core.agent.agent as agent_module
from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.llm.manager import ProviderOverrides
from rpg_world.rpg_core.agent.agent_types import (
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
async def test_ensure_initialized_is_idempotent(monkeypatch):
    class FakePromptManager:
        def __init__(self, _world_name: str) -> None:
            self.system_prompt = "system"

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

    monkeypatch.setattr(agent_module, "PromptManager", FakePromptManager)
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
    agent._workspace = "data/test"
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


def test_rpg_game_agent_default_model_no_longer_forces_gpt4o(monkeypatch):
    monkeypatch.setattr(agent_module.RPGGameAgent, "_refresh_rpg_context", lambda self: None)

    agent = RPGGameAgent(
        session_id="test",
        workspace="data/test",
        model=None,
    )

    assert agent._model is None
    assert agent._provider_overrides == ProviderOverrides()


@pytest.mark.asyncio
async def test_ensure_initialized_populates_model_from_provider(monkeypatch):
    class FakePromptManager:
        def __init__(self, _world_name: str) -> None:
            self.system_prompt = "system"

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

    monkeypatch.setattr(agent_module, "PromptManager", FakePromptManager)
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
    agent._workspace = "data/test"
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
