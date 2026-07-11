from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import rpg_core.agent.agent as agent_module
import rpg_core.agent.transaction.transaction as transaction_module
from commons.errors import (
    MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE,
    MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE,
    TURN_METADATA_INVALID_ERROR_CODE,
    TURN_METADATA_INVALID_STATUS_CODE,
    MainContextWindowThresholdExceededError,
)
from rpg_core.agent.transaction.commit_plan import TurnCommitPlan
from rpg_core.agent.transaction.message_scratch import MessageScratch
from rpg_core.agent.transaction.status_scratch import StatusDocumentScratch
from rpg_data.models import StatusTableDocument
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.agent.command import CommandDispatcher
from rpg_core.agent.tools import BaseTool
from rpg_core.context.rpg_context import (
    FixedLayerData,
    HotHistoryLayer,
    Message,
    RPGContext,
    Role,
    UserMessageLayer,
)
from rpg_core.context.fixed_layer import FIXED_LAYER_CORE_SECTION_ID, FixedLayerSection
from rpg_core.session.manager import SessionManager
from rpg_core.session.turn_metadata import InvalidTurnMetadataError
from llm_service.manager import ProviderOverrides
from rpg_core.context.fixed_layer.contributors import (
    STORY_PROMPT_SECTION_ID,
    STORY_PROMPT_SOURCE,
    TEXT_OUTPUT_FORMAT_SECTION_ID,
)
from rpg_core.rp_modules.constants import (
    RP_MODULE_DICE_SECTION_ID,
)
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.settings import RPModuleSettings
from rpg_core.agent.agent_types import (
    AgentStreamEvent,
    QueueItem,
    QueueKind,
    StreamEventKind,
    TurnCancelStatus,
    _StreamSentinel,
)


def _init_stream_cancel_state(agent: RPGGameAgent, *, session_id: str = "s_cancel") -> None:
    agent._session_id = session_id
    agent._active_stream_task = None
    agent._active_stream_request_id = None
    agent._queued_stream_request_ids = set()
    agent._cancelled_request_ids = set()


def _patch_story_prompt_contributor(monkeypatch, content: str = "") -> None:
    class FakeStoryPromptContributor:
        name = STORY_PROMPT_SOURCE

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_fixed_contribution(self):
            from rpg_core.context.fixed_layer import FixedLayerContribution

            sections = []
            if content:
                sections.append(FixedLayerSection(
                    id=STORY_PROMPT_SECTION_ID,
                    title="故事固定提示词",
                    content=content,
                    priority=10,
                    source=STORY_PROMPT_SOURCE,
                    source_kind=STORY_PROMPT_SOURCE,
                    item_count=1,
                ))
            return FixedLayerContribution(sections=sections)

    monkeypatch.setattr(agent_module, "StoryPromptFixedLayerContributor", FakeStoryPromptContributor)


@pytest.mark.asyncio
async def test_queue_consumer_surfaces_stream_errors(monkeypatch):
    agent = object.__new__(RPGGameAgent)
    _init_stream_cancel_state(agent)
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
async def test_queue_consumer_surfaces_turn_metadata_stream_error(monkeypatch):
    agent = object.__new__(RPGGameAgent)
    _init_stream_cancel_state(agent)
    agent._queue = asyncio.Queue()
    agent._cmd_dispatcher = None
    agent._send_impl = AsyncMock()
    agent._send_stream_impl = AsyncMock(side_effect=InvalidTurnMetadataError("bad turn metadata"))

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
        assert first.error_code == TURN_METADATA_INVALID_ERROR_CODE
        assert first.status_code == TURN_METADATA_INVALID_STATUS_CODE
        assert first.content == "bad turn metadata"
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
async def test_cancel_current_turn_cancels_active_stream_request() -> None:
    agent = object.__new__(RPGGameAgent)
    _init_stream_cancel_state(agent)
    started = asyncio.Event()

    async def active_stream() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(active_stream())
    await asyncio.wait_for(started.wait(), timeout=1)
    agent._active_stream_task = task
    agent._active_stream_request_id = "req-active"

    result = await agent.cancel_current_turn(request_id="req-active")

    assert result.status == TurnCancelStatus.CANCELLED
    assert result.request_id == "req-active"
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancel_current_turn_ignores_stale_request_id() -> None:
    agent = object.__new__(RPGGameAgent)
    _init_stream_cancel_state(agent)
    task = asyncio.create_task(asyncio.Event().wait())
    agent._active_stream_task = task
    agent._active_stream_request_id = "req-new"

    try:
        result = await agent.cancel_current_turn(request_id="req-old")

        assert result.status == TurnCancelStatus.STALE
        assert not task.cancelled()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_queue_consumer_skips_cancelled_queued_stream() -> None:
    agent = object.__new__(RPGGameAgent)
    _init_stream_cancel_state(agent)
    agent._queue = asyncio.Queue()
    agent._cmd_dispatcher = None
    agent._send_impl = AsyncMock()
    agent._send_stream_impl = AsyncMock()

    future = asyncio.get_running_loop().create_future()
    event_queue: asyncio.Queue = asyncio.Queue()
    request_id = "req-queued"
    agent._queued_stream_request_ids.add(request_id)
    await agent._queue.put(
        QueueItem(
            kind=QueueKind.SEND_STREAM,
            user_input="hello",
            future=future,
            event_queue=event_queue,
            request_id=request_id,
        )
    )

    cancel_result = await agent.cancel_current_turn(request_id=request_id)
    consumer_task = asyncio.create_task(agent._queue_consumer())
    try:
        sentinel = await asyncio.wait_for(event_queue.get(), timeout=1)

        assert cancel_result.status == TurnCancelStatus.CANCELLED
        assert isinstance(sentinel, _StreamSentinel)
        assert future.done()
        assert future.result() is None
        agent._send_stream_impl.assert_not_awaited()
    finally:
        consumer_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer_task


def _make_transaction_agent(
    monkeypatch,
    *,
    history: list[Message] | None = None,
    status_mgr=None,
    scene_tracker=None,
):
    class FakeBuiltContext:
        def __init__(self, messages):
            self._messages = list(messages)

        def to_message_objects(self):
            return list(self._messages)

    class FakeBuilder:
        def __init__(self) -> None:
            self.calls = []

        def build(
            self,
            *,
            history_messages,
            current_user_message,
            status_mgr=None,
            scene_tracker=None,
            **kwargs,
        ):  # noqa: ANN001
            messages = [
                *history_messages,
                *([current_user_message] if current_user_message else []),
            ]
            self.calls.append({
                "messages": list(messages),
                "status_mgr": status_mgr,
                "scene_tracker": scene_tracker,
                "kwargs": kwargs,
            })
            return FakeBuiltContext(messages)

    monkeypatch.setattr(
        agent_module,
        "settings",
        SimpleNamespace(
            verbose_logging=False,
            include_tool_records=True,
            context_window_reject_threshold_ratio=0.9,
        ),
    )

    session = SessionManager(history_enabled=False)
    session.replace_history(list(history or []), persist=False)

    agent = object.__new__(RPGGameAgent)
    agent._cmd_dispatcher = None
    agent._player_character_guard_reply = lambda: ""
    agent._session_id = "s_tx"
    agent._model = "test-model"
    agent._session = session
    agent._status_mgr = status_mgr
    agent._scene_tracker = scene_tracker
    agent._status_sub_agent = None
    agent._memory_manager = None
    agent._memory_sub_agent = None
    agent._compressor = None
    agent._builder = FakeBuilder()
    agent._fixed_layer = FixedLayerData()
    agent._refresh_fixed_layer_snapshot = MagicMock()
    agent._rp_module_registry = None
    agent._tool_registry = agent_module.ToolRegistry()
    agent._provider = object()
    agent._main_llm_selection_service = SimpleNamespace(
        resolve_session=lambda _session_id: SimpleNamespace(
            effective_provider_key="test_chat",
            effective_source="config",
            effective=SimpleNamespace(context_window=64_000),
        )
    )
    agent._token_counter = SimpleNamespace(
        count_messages=lambda messages: sum(len(message.content) for message in messages)
    )
    agent._refresh_main_provider = lambda *, selection=None: agent._provider
    agent._last_tool_records = None
    return agent


def test_turn_transaction_begin_failure_clears_active_turn(monkeypatch):
    session = SessionManager(history_enabled=False)
    tx = transaction_module.AgentTurnTransaction(
        session=session,
        status_mgr=None,
        scene_tracker=None,
    )

    def fail_message_scratch(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("scratch failed")

    monkeypatch.setattr(transaction_module, "MessageScratch", fail_message_scratch)

    with pytest.raises(RuntimeError, match="scratch failed"):
        tx.begin(SimpleNamespace())

    assert session.begin_turn() == 1
    session.end_turn(1)


def test_turn_commit_plan_restores_history_on_turn_metadata_error() -> None:
    session = SessionManager(history_enabled=False)
    session.append(Role.USER, "base", turn_id=1, seq_in_turn=1)
    scratch = MessageScratch(
        turn_id=2,
        base_history=session.history,
        staged_messages=[
            Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
            Message(Role.ASSISTANT, "duplicate", turn_id=2, seq_in_turn=1),
        ],
    )
    plan = TurnCommitPlan(
        session=session,
        status_mgr=None,
        message_scratch=scratch,
        status_scratch=StatusDocumentScratch(None),
    )

    with pytest.raises(InvalidTurnMetadataError, match="seq_in_turn must increase"):
        plan.commit()

    assert [message.content for message in session.history] == ["base"]


@pytest.mark.asyncio
async def test_send_impl_commits_history_only_after_llm_success(monkeypatch):
    history = [
        Message(Role.USER, "old", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "old reply", turn_id=1, seq_in_turn=2),
    ]
    agent = _make_transaction_agent(monkeypatch, history=history)
    post_commit = SimpleNamespace(maybe_auto_extract=AsyncMock())
    agent._memory_sub_agent = post_commit
    seen_messages: list[Message] = []

    async def fake_run_chat_loop(**kwargs):  # noqa: ANN001
        assert [message.content for message in agent._session.history] == ["old", "old reply"]
        seen_messages.extend(kwargs["messages"])
        return "new reply", []

    monkeypatch.setattr(agent_module, "run_chat_loop", fake_run_chat_loop)

    reply = await agent._send_impl("look around")

    assert reply.text == "new reply"
    assert [message.content for message in seen_messages] == ["old", "old reply", "look around"]
    assert [(message.content, message.turn_id, message.seq_in_turn) for message in agent._session.history] == [
        ("old", 1, 1),
        ("old reply", 1, 2),
        ("look around", 2, 1),
        ("new reply", 2, 2),
    ]
    post_commit.maybe_auto_extract.assert_awaited_once_with(agent._session)


@pytest.mark.asyncio
async def test_send_impl_discards_turn_scratch_when_llm_fails(monkeypatch):
    history = [Message(Role.USER, "old", turn_id=1, seq_in_turn=1)]
    agent = _make_transaction_agent(monkeypatch, history=history)
    post_commit = SimpleNamespace(maybe_auto_extract=AsyncMock())
    agent._memory_sub_agent = post_commit

    async def fake_run_chat_loop(**_kwargs):  # noqa: ANN001
        assert [message.content for message in agent._session.history] == ["old"]
        raise RuntimeError("llm failed")

    monkeypatch.setattr(agent_module, "run_chat_loop", fake_run_chat_loop)

    with pytest.raises(RuntimeError, match="llm failed"):
        await agent._send_impl("do it")

    assert [(message.content, message.turn_id, message.seq_in_turn) for message in agent._session.history] == [
        ("old", 1, 1),
    ]
    post_commit.maybe_auto_extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_provider_switch_applies_next_turn_and_is_fixed_for_current_turn(monkeypatch):
    agent = _make_transaction_agent(monkeypatch)

    class FakeProvider:
        def __init__(self, name: str) -> None:
            self.name = name

        def get_default_model(self) -> str:
            return self.name

    providers = {
        "chat_a": FakeProvider("model-a"),
        "chat_b": FakeProvider("model-b"),
    }
    current_key = {"value": "chat_a"}
    manager_calls: list[str] = []

    def selection():
        key = current_key["value"]
        return SimpleNamespace(
            effective_provider_key=key,
            effective_source="session",
            effective=SimpleNamespace(context_window=64000),
        )

    class FakeManager:
        def get_provider(self, biz_key, overrides=None, *, provider_key=None):  # noqa: ANN001
            assert biz_key == "agent.main"
            assert overrides == ProviderOverrides()
            manager_calls.append(provider_key)
            return providers[provider_key]

    agent._main_llm_selection_service = SimpleNamespace(
        resolve_session=lambda _session_id: selection()
    )
    agent._main_llm_selection = None
    agent._provider_overrides = ProviderOverrides()
    agent._provider = None
    agent._refresh_main_provider = RPGGameAgent._refresh_main_provider.__get__(
        agent,
        RPGGameAgent,
    )
    monkeypatch.setattr(agent_module.LLMManager, "get", classmethod(lambda cls: FakeManager()))

    providers_seen_by_turn: list[FakeProvider] = []

    async def fake_run_chat_loop(**kwargs):  # noqa: ANN001
        providers_seen_by_turn.append(kwargs["provider"])
        if len(providers_seen_by_turn) == 1:
            current_key["value"] = "chat_b"
        return f"reply-{len(providers_seen_by_turn)}", []

    monkeypatch.setattr(agent_module, "run_chat_loop", fake_run_chat_loop)

    await agent._send_impl("first")
    await agent._send_impl("second")

    assert providers_seen_by_turn == [providers["chat_a"], providers["chat_b"]]
    assert manager_calls == ["chat_a", "chat_b"]
    assert agent._provider is providers["chat_b"]
    assert agent._model == "model-b"


@pytest.mark.asyncio
async def test_context_preview_uses_latest_effective_main_llm_window(monkeypatch):
    captured: dict[str, object] = {}

    class FakeInspector:
        def __init__(self, ctx, token_counter, *, hot_history_rounds, context_limit):  # noqa: ANN001
            captured.update(
                ctx=ctx,
                token_counter=token_counter,
                hot_history_rounds=hot_history_rounds,
                context_limit=context_limit,
            )

        def to_payload(self, *, session_id: str) -> dict[str, object]:
            return {"sessionId": session_id, "contextLimit": captured["context_limit"]}

    monkeypatch.setattr(agent_module, "ContextInspector", FakeInspector)

    agent = object.__new__(RPGGameAgent)
    agent._ensure_initialized = AsyncMock()
    agent._build_ctx_for_inspection = MagicMock(return_value="ctx")
    agent._resolve_main_llm_selection = lambda: SimpleNamespace(
        effective=SimpleNamespace(context_window=8192)
    )
    agent._token_counter = "counter"
    agent._builder = SimpleNamespace(config=SimpleNamespace(hot_history_rounds=7))
    agent._session_id = "s_preview"

    payload = await agent.get_context_payload()

    assert payload == {"sessionId": "s_preview", "contextLimit": 8192}
    assert captured == {
        "ctx": "ctx",
        "token_counter": "counter",
        "hot_history_rounds": 7,
        "context_limit": 8192,
    }


@pytest.mark.asyncio
async def test_context_threshold_excludes_current_turn_input(monkeypatch) -> None:
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, "12345678", turn_id=1, seq_in_turn=1)],
    )
    agent._main_llm_selection_service = SimpleNamespace(
        resolve_session=lambda _session_id: SimpleNamespace(
            effective_provider_key="small_chat",
            effective_source="session",
            effective=SimpleNamespace(context_window=10),
        )
    )
    huge_input = "x" * 100
    seen_messages: list[Message] = []

    async def fake_run_chat_loop(**kwargs):  # noqa: ANN001
        seen_messages.extend(kwargs["messages"])
        return "accepted", []

    monkeypatch.setattr(agent_module, "run_chat_loop", fake_run_chat_loop)

    reply = await agent._send_impl(huge_input)

    assert reply.text == "accepted"
    assert [message.content for message in agent._builder.calls[0]["messages"]] == ["12345678"]
    assert seen_messages[-1].content == huge_input


@pytest.mark.asyncio
@pytest.mark.parametrize("history_text", ["123456789", "1234567890"])
async def test_context_threshold_rejects_at_or_above_boundary_before_turn(
    monkeypatch,
    history_text: str,
) -> None:
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, history_text, turn_id=1, seq_in_turn=1)],
    )
    agent._main_llm_selection_service = SimpleNamespace(
        resolve_session=lambda _session_id: SimpleNamespace(
            effective_provider_key="small_chat",
            effective_source="session",
            effective=SimpleNamespace(context_window=10),
        )
    )
    agent._refresh_main_provider = MagicMock(return_value=agent._provider)

    with pytest.raises(MainContextWindowThresholdExceededError) as exc_info:
        await agent._send_impl("new body")

    stream_events: asyncio.Queue = asyncio.Queue()
    with pytest.raises(MainContextWindowThresholdExceededError):
        await agent._send_stream_impl("new body", stream_events)

    assert exc_info.value.used_tokens == len(history_text)
    assert exc_info.value.context_limit == 10
    assert stream_events.empty()
    assert [message.content for message in agent._session.history] == [history_text]
    assert agent._session._active_turn_id is None
    agent._refresh_main_provider.assert_not_called()


@pytest.mark.asyncio
async def test_context_threshold_always_allows_slash_commands(monkeypatch) -> None:
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, "1234567890", turn_id=1, seq_in_turn=1)],
    )
    agent._cmd_dispatcher = SimpleNamespace(
        is_command=lambda text: text.lstrip().startswith("/"),
        dispatch=AsyncMock(return_value=agent_module.CommandResult(reply="compacted", handled=True)),
    )
    agent._resolve_main_llm_selection = MagicMock()

    reply = await agent._send_impl("   /compact")

    stream_events: asyncio.Queue = asyncio.Queue()
    await agent._send_stream_impl("   /compact", stream_events)
    text_event = await stream_events.get()
    done_event = await stream_events.get()

    assert reply.text == "compacted"
    assert text_event.kind == StreamEventKind.TEXT
    assert text_event.content == "compacted"
    assert done_event.kind == StreamEventKind.DONE
    assert done_event.content == "compacted"
    agent._resolve_main_llm_selection.assert_not_called()


def test_context_threshold_stream_error_keeps_code_and_message_separate() -> None:
    error = MainContextWindowThresholdExceededError(
        used_tokens=90,
        context_limit=100,
        threshold_ratio=0.9,
    )

    event = RPGGameAgent._stream_error_event(error)

    assert event.kind == StreamEventKind.ERROR
    assert event.error_code == MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE
    assert event.status_code == MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE
    assert event.content == str(error)
    assert MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE not in event.content


class _FakeStatusManager:
    session_id = "s_tx"

    def __init__(self, *, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.document = StatusTableDocument.from_data(
            SimpleNamespace(headers=("key", "value"), rows=(("位置", "旧地"),))
        )

    def _table(self):
        return {
            "id": 1,
            "name": "当前场景",
            "status_kind": "scene",
            "headers": list(self.document.headers),
            "rows": [list(row) for row in self.document.data_rows],
            "document": self.document.to_json_dict(),
        }

    def list_context_tables(self):
        return []

    def get_active_scene_table_ref(self):
        return 1, ("scene", "当前场景")

    def get_active_scene_table(self):
        return self.get_table_by_id(1)

    def get_table_by_id(self, table_id: int):
        assert int(table_id) == 1
        return self._table()

    def get_table_document_by_id(self, table_id: int):
        assert int(table_id) == 1
        return self.document

    def save_table_document(self, table_id: int, document, **_kwargs):
        assert int(table_id) == 1
        if self.fail_commit:
            raise RuntimeError("status commit failed")
        self.document = document
        return self._table()

    def get_scene_attrs(self):
        return {row.key: row.value for row in self.document.rows}

    def runtime_set_key_value(self, table_id: int, key: str, value: str, **_kwargs):
        if self.fail_commit:
            raise RuntimeError("status commit failed")
        self.document = self.document.with_key_value(key, value)
        return self._table()

    def runtime_delete_key_value(self, table_id: int, key: str, **_kwargs):
        if self.fail_commit:
            raise RuntimeError("status commit failed")
        self.document = self.document.without_key(key)
        return self._table()


class _ScratchWritingStatusSubAgent:
    def __init__(self) -> None:
        self._tool_registry = agent_module.ToolRegistry()
        self._schemas = []

    def clear_tools(self) -> None:
        self._tool_registry = agent_module.ToolRegistry()
        self._schemas = []

    def register_tools(self, tools) -> None:  # noqa: ANN001
        self._tool_registry.register_all(tools)
        self._schemas = self._tool_registry.get_openai_schemas()

    async def update(self, *, history, state_context, user_input, turn_stats):  # noqa: ANN001
        assert [message.content for message in history] == ["old"]
        assert "位置: 旧地" in state_context
        await self._tool_registry.execute("scene_attr", '{"key":"位置","value":"新地"}')
        return SimpleNamespace(
            updated=True,
            records=[{"tool_name": "scene_attr", "arguments": "{}", "result": "ok"}],
        )


class _FakeNormalStatusManager:
    session_id = "s_tx"

    def __init__(self) -> None:
        self.document = StatusTableDocument.from_data(
            SimpleNamespace(headers=("属性", "值"), rows=(("生命", "10"),))
        )

    def _table(self):
        return {
            "id": 7,
            "name": "角色状态",
            "status_kind": "normal",
            "description": "追踪生命",
            "headers": list(self.document.headers),
            "rows": [list(row) for row in self.document.data_rows],
            "document": self.document.to_json_dict(),
            "metadata_json": "{}",
        }

    def list_context_tables(self):
        return [self._table()]

    def get_active_scene_table_ref(self):
        return None

    def get_table_by_id(self, table_id: int):
        assert table_id == 7
        return self._table()

    def get_table_document_by_id(self, table_id: int):
        assert table_id == 7
        return self.document

    def save_table_document(self, table_id: int, document, **_kwargs):
        assert table_id == 7
        self.document = document
        return self._table()


class _NormalScratchWritingStatusSubAgent(_ScratchWritingStatusSubAgent):
    async def update(self, *, history, state_context, user_input, turn_stats):  # noqa: ANN001
        assert "运行时表 ID：7" in state_context
        result = await self._tool_registry.execute(
            "status_table_set_values",
            '{"table_id":7,"updates":[{"key":"生命","value":"8"}]}',
        )
        return SimpleNamespace(
            updated=True,
            records=[{
                "tool_name": "status_table_set_values",
                "arguments": "{}",
                "result": result,
                "changed": True,
            }],
        )


class _NormalNoOpStatusSubAgent(_ScratchWritingStatusSubAgent):
    async def update(self, *, history, state_context, user_input, turn_stats):  # noqa: ANN001
        result = await self._tool_registry.execute(
            "status_table_set_values",
            '{"table_id":7,"updates":[{"key":"生命","value":"10"}]}',
        )
        return SimpleNamespace(
            updated=False,
            records=[{
                "tool_name": "status_table_set_values",
                "arguments": "{}",
                "result": result,
                "changed": False,
                "status": "no_op",
            }],
        )


def _scene_tracker_for(status_mgr):
    from rpg_core.scene import SceneTracker

    tracker = SceneTracker()
    tracker.bind_status_manager(status_mgr)
    tracker.load_from_status_table()
    return tracker


@pytest.mark.asyncio
async def test_status_sub_agent_writes_status_scratch_before_commit(monkeypatch):
    status_mgr = _FakeStatusManager()
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, "old", turn_id=1, seq_in_turn=1)],
        status_mgr=status_mgr,
        scene_tracker=_scene_tracker_for(status_mgr),
    )
    agent._status_sub_agent = _ScratchWritingStatusSubAgent()
    seen_user_content = ""

    async def fake_run_chat_loop(**kwargs):  # noqa: ANN001
        nonlocal seen_user_content
        assert status_mgr.get_scene_attrs()["位置"] == "旧地"
        seen_user_content = kwargs["messages"][-1].content
        return "done", []

    monkeypatch.setattr(agent_module, "run_chat_loop", fake_run_chat_loop)

    await agent._send_impl("go")

    assert "位置: 新地" in seen_user_content
    assert status_mgr.get_scene_attrs()["位置"] == "新地"


@pytest.mark.asyncio
async def test_status_sub_agent_updates_normal_table_without_scene(monkeypatch):
    status_mgr = _FakeNormalStatusManager()
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, "old", turn_id=1, seq_in_turn=1)],
        status_mgr=status_mgr,
        scene_tracker=None,
    )
    agent._status_sub_agent = _NormalScratchWritingStatusSubAgent()

    async def fake_run_chat_loop(**kwargs):  # noqa: ANN001
        assert status_mgr.document.data_rows == (("生命", "10"),)
        scratch_manager = agent._builder.calls[-1]["status_mgr"]
        assert scratch_manager.list_context_tables()[0]["rows"] == [["生命", "8"]]
        assert "status_table_set_values" in kwargs["tool_registry"]
        return "done", []

    monkeypatch.setattr(agent_module, "run_chat_loop", fake_run_chat_loop)

    await agent._send_impl("受伤")

    assert status_mgr.document.data_rows == (("生命", "8"),)


@pytest.mark.asyncio
async def test_send_stream_emits_status_sub_agent_no_op_records(monkeypatch):
    status_mgr = _FakeNormalStatusManager()
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, "old", turn_id=1, seq_in_turn=1)],
        status_mgr=status_mgr,
        scene_tracker=None,
    )
    agent._status_sub_agent = _NormalNoOpStatusSubAgent()

    async def fake_run_chat_loop_stream(**_kwargs):  # noqa: ANN001
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="done")
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content="done")

    monkeypatch.setattr(agent_module, "run_chat_loop_stream", fake_run_chat_loop_stream)
    event_queue: asyncio.Queue = asyncio.Queue()

    await agent._send_stream_impl("保持状态", event_queue)

    events = [await event_queue.get() for _ in range(5)]
    assert [getattr(event, "kind", None) for event in events[:4]] == [
        StreamEventKind.TOOL_CALL,
        StreamEventKind.TOOL_RESULT,
        StreamEventKind.TEXT,
        StreamEventKind.DONE,
    ]
    assert isinstance(events[-1], _StreamSentinel)
    assert status_mgr.document.data_rows == (("生命", "10"),)


@pytest.mark.asyncio
async def test_send_stream_commits_before_done_event(monkeypatch):
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, "old", turn_id=1, seq_in_turn=1)],
    )
    done_history_snapshots: list[list[str]] = []

    class InspectQueue(asyncio.Queue):
        async def put(self, item):  # noqa: ANN001
            if isinstance(item, AgentStreamEvent) and item.kind == StreamEventKind.DONE:
                done_history_snapshots.append([message.content for message in agent._session.history])
            await super().put(item)

    async def fake_run_chat_loop_stream(**_kwargs):  # noqa: ANN001
        assert [message.content for message in agent._session.history] == ["old"]
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="part")
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content="final")

    monkeypatch.setattr(agent_module, "run_chat_loop_stream", fake_run_chat_loop_stream)

    event_queue: asyncio.Queue = InspectQueue()
    await agent._send_stream_impl("go", event_queue)

    assert done_history_snapshots == [["old", "go", "final"]]
    first = await event_queue.get()
    second = await event_queue.get()
    third = await event_queue.get()
    assert first.kind == StreamEventKind.TEXT
    assert second.kind == StreamEventKind.DONE
    assert isinstance(third, _StreamSentinel)


@pytest.mark.asyncio
async def test_send_stream_cancellation_discards_turn_scratch(monkeypatch):
    status_mgr = _FakeStatusManager()
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, "old", turn_id=1, seq_in_turn=1)],
        status_mgr=status_mgr,
        scene_tracker=_scene_tracker_for(status_mgr),
    )
    agent._status_sub_agent = _ScratchWritingStatusSubAgent()
    release_stream = asyncio.Event()

    async def fake_run_chat_loop_stream(**_kwargs):  # noqa: ANN001
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="part")
        await release_stream.wait()
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content="final")

    monkeypatch.setattr(agent_module, "run_chat_loop_stream", fake_run_chat_loop_stream)

    event_queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(agent._send_stream_impl("go", event_queue))
    events = [await asyncio.wait_for(event_queue.get(), timeout=1) for _ in range(3)]

    assert [event.kind for event in events] == [
        StreamEventKind.TOOL_CALL,
        StreamEventKind.TOOL_RESULT,
        StreamEventKind.TEXT,
    ]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert [message.content for message in agent._session.history] == ["old"]
    assert status_mgr.get_scene_attrs()["位置"] == "旧地"


@pytest.mark.asyncio
async def test_send_stream_commit_failure_emits_error_without_done(monkeypatch):
    status_mgr = _FakeStatusManager(fail_commit=True)
    agent = _make_transaction_agent(
        monkeypatch,
        history=[Message(Role.USER, "old", turn_id=1, seq_in_turn=1)],
        status_mgr=status_mgr,
        scene_tracker=_scene_tracker_for(status_mgr),
    )
    agent._status_sub_agent = _ScratchWritingStatusSubAgent()
    event_queue: asyncio.Queue = asyncio.Queue()

    async def fake_run_chat_loop_stream(**kwargs):  # noqa: ANN001
        assert [message.content for message in agent._session.history] == ["old"]
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="part")
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content="final")

    monkeypatch.setattr(agent_module, "run_chat_loop_stream", fake_run_chat_loop_stream)

    await agent._send_stream_impl("go", event_queue)

    events = [await event_queue.get(), await event_queue.get(), await event_queue.get(), await event_queue.get()]
    assert [getattr(event, "kind", None) for event in events] == [
        StreamEventKind.TOOL_CALL,
        StreamEventKind.TOOL_RESULT,
        StreamEventKind.TEXT,
        StreamEventKind.ERROR,
    ]
    assert isinstance(await event_queue.get(), _StreamSentinel)
    assert "status commit failed" in events[-1].content
    assert [message.content for message in agent._session.history] == ["old"]
    assert status_mgr.get_scene_attrs()["位置"] == "旧地"


@pytest.mark.asyncio
async def test_send_stream_command_reply_emits_text_before_done():
    event_queue: asyncio.Queue = asyncio.Queue()
    fake_agent = SimpleNamespace()
    dispatcher = CommandDispatcher(agent=fake_agent)
    dispatcher.register_default_builtins()
    fake_agent.list_commands = dispatcher.list_commands
    agent = object.__new__(RPGGameAgent)
    agent._cmd_dispatcher = dispatcher
    agent._model = "test-model"

    await agent._send_stream_impl("/help", event_queue)

    first = await event_queue.get()
    second = await event_queue.get()
    third = await event_queue.get()

    assert isinstance(first, AgentStreamEvent)
    assert first.kind == StreamEventKind.TEXT
    assert "可用命令:" in first.content
    assert isinstance(second, AgentStreamEvent)
    assert second.kind == StreamEventKind.DONE
    assert second.content == first.content
    assert isinstance(third, _StreamSentinel)


def test_compose_stored_user_input_places_user_text_after_scene_close_tag() -> None:
    scene_ctx = "[scene]\n位置: 北境森林\n[/scene]"

    assert RPGGameAgent._compose_stored_user_input(scene_ctx, "我观察四周") == (
        "[scene]\n位置: 北境森林\n[/scene]\n我观察四周"
    )


@pytest.mark.asyncio
async def test_ensure_initialized_is_idempotent(monkeypatch):
    class FakeCoreRPContractContributor:
        name = "core"

        def __init__(self, _world_name: str) -> None:
            self.sections = []

        def get_fixed_contribution(self):
            from rpg_core.context.fixed_layer import FixedLayerContribution

            return FixedLayerContribution(sections=self.sections)

    class FakeSubAgent:
        calls: list[dict[str, object]] = []

        def __init__(self, *args, **kwargs) -> None:
            self.calls.append(dict(kwargs))
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

    class FakeProvider:
        def get_default_model(self) -> str:
            return "selected-model"

    class FakeManager:
        def get_provider(self, biz_key, overrides=None, *, provider_key=None):  # noqa: ANN001
            assert biz_key == "agent.main"
            assert overrides == ProviderOverrides(openai_model="gpt-4o")
            assert provider_key == "main_chat"
            return FakeProvider()

    _patch_story_prompt_contributor(monkeypatch)
    monkeypatch.setattr(agent_module, "CoreRPContractContributor", FakeCoreRPContractContributor)
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
    agent._provider_overrides = ProviderOverrides(openai_model="gpt-4o")
    agent._main_llm_selection_service = SimpleNamespace(
        resolve_session=lambda _session_id: SimpleNamespace(
            effective_provider_key="main_chat",
            effective_source="config",
        )
    )
    agent._main_llm_selection = None
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
    assert len(FakeSubAgent.calls) == 2
    assert all("provider_overrides" not in kwargs for kwargs in FakeSubAgent.calls)


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


def test_setup_rp_module_registry_adds_fixed_sections(monkeypatch):
    _patch_story_prompt_contributor(monkeypatch, "故事固定约束。")

    agent = object.__new__(RPGGameAgent)
    agent._session_id = "s1"
    agent._world_name = "world"
    agent._builder = SimpleNamespace(config=SimpleNamespace(enable_lorebook=True, enable_character=True))
    agent._status_mgr = None
    agent._scene_tracker = None
    agent._character_mgr = None
    agent._lorebook_mgr = None

    agent._setup_rp_module_registry()

    assert agent._rp_module_registry is not None
    assert any(section.id == STORY_PROMPT_SECTION_ID for section in agent._fixed_layer.sections)
    assert any(section.id == RP_MODULE_DICE_SECTION_ID for section in agent._fixed_layer.sections)
    assert any(section.id == TEXT_OUTPUT_FORMAT_SECTION_ID for section in agent._fixed_layer.sections)


def test_assemble_fixed_layer_reads_story_prompt_from_data_service(monkeypatch):
    class FakeCatalog:
        def get_session_story(self, session_id: str):  # noqa: ANN201
            assert session_id == "s1"
            return SimpleNamespace(story_prompt="雾港故事固定提示词。")

    class FakeGateway:
        catalog = FakeCatalog()

    import rpg_data.services as data_services

    monkeypatch.setattr(data_services, "get_data_service_gateway", lambda: FakeGateway())

    agent = object.__new__(RPGGameAgent)
    agent._session_id = "s1"
    agent._world_name = "world"
    agent._builder = SimpleNamespace(config=SimpleNamespace(enable_lorebook=True, enable_character=True))
    agent._character_mgr = None
    agent._lorebook_mgr = None
    agent._rp_module_registry = None

    fixed_layer = agent._assemble_fixed_layer()

    story_section = next(section for section in fixed_layer.sections if section.id == STORY_PROMPT_SECTION_ID)
    assert story_section.content == "雾港故事固定提示词。"
    assert [section.id for section in fixed_layer.sections][:2] == [
        FIXED_LAYER_CORE_SECTION_ID,
        STORY_PROMPT_SECTION_ID,
    ]


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

        def build(self, *, history_messages, current_user_message, **_kwargs):  # noqa: ANN001
            self.last_messages = history_messages
            return RPGContext(
                hot_history=HotHistoryLayer(messages=list(history_messages)),
                user_message=UserMessageLayer(
                    user_input=current_user_message.content if current_user_message else ""
                ),
            )

    history = [Message(Role.USER, "old", turn_id=1, seq_in_turn=1)]
    builder = FakeBuilder()
    agent = object.__new__(RPGGameAgent)
    agent._ensure_initialized = AsyncMock()
    agent._session_id = "s_json"
    agent._token_counter = fake_token_counter
    agent._builder = builder
    agent._fixed_layer = FixedLayerData()
    agent._refresh_fixed_layer_snapshot = MagicMock()
    agent._session = SimpleNamespace(
        history=history,
        context_history=lambda: SimpleNamespace(
            messages=tuple(history),
            filtered_message_count=0,
        ),
    )
    agent._status_mgr = None
    agent._scene_tracker = None
    agent._rp_module_registry = None
    agent._resolve_main_llm_selection = lambda: SimpleNamespace(
        effective=SimpleNamespace(context_window=64000)
    )

    payload = json.loads(await agent.get_context_json("preview"))

    agent._refresh_fixed_layer_snapshot.assert_called_once()
    assert [message.content for message in history] == ["old"]
    assert builder.last_messages is not history
    assert [message.content for message in builder.last_messages] == ["old"]
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


def test_build_transformed_context_rebuilds_fixed_layer_each_time() -> None:
    class FakeBuilder:
        config = SimpleNamespace(hot_history_rounds=2)

        def __init__(self) -> None:
            self.fixed_layer = None

        def build(self, *, fixed_layer, **_kwargs):  # noqa: ANN001
            self.fixed_layer = fixed_layer
            return RPGContext(fixed_layer=fixed_layer)

    first_layer = FixedLayerData(
        sections=[FixedLayerSection(id="fresh", title="Fresh", content="fresh fixed")]
    )
    second_layer = FixedLayerData(
        sections=[FixedLayerSection(id="fresher", title="Fresher", content="fresher fixed")]
    )
    builder = FakeBuilder()
    agent = object.__new__(RPGGameAgent)
    agent._session_id = "s1"
    agent._builder = builder
    agent._fixed_layer = FixedLayerData()
    agent._assemble_fixed_layer = MagicMock(side_effect=[first_layer, second_layer])
    agent._refresh_sub_agent_contexts = MagicMock()
    history = [Message(Role.USER, "hello")]
    agent._session = SimpleNamespace(
        history=history,
        context_history=lambda: SimpleNamespace(
            messages=tuple(history),
            filtered_message_count=0,
        ),
    )
    agent._status_mgr = None
    agent._scene_tracker = None
    agent._rp_module_registry = None

    first_messages = agent._build_transformed_context()
    second_messages = agent._build_transformed_context()

    assert agent._assemble_fixed_layer.call_count == 2
    assert agent._refresh_sub_agent_contexts.call_count == 2
    assert agent._fixed_layer is second_layer
    assert builder.fixed_layer is second_layer
    assert first_messages[0].is_system()
    assert "fresh fixed" in first_messages[0].content
    assert "fresher fixed" in second_messages[0].content


def test_context_inspection_rebuilds_fixed_layer_each_time() -> None:
    class FakeBuilder:
        config = SimpleNamespace(hot_history_rounds=2)

        def __init__(self) -> None:
            self.fixed_layer = None

        def build(
            self,
            *,
            fixed_layer,
            history_messages,
            current_user_message,
            **_kwargs,
        ):  # noqa: ANN001
            self.fixed_layer = fixed_layer
            return RPGContext(
                fixed_layer=fixed_layer,
                hot_history=HotHistoryLayer(messages=[
                    *history_messages,
                    *([current_user_message] if current_user_message else []),
                ]),
            )

    first_layer = FixedLayerData(
        sections=[FixedLayerSection(id="fresh", title="Fresh", content="fresh fixed")]
    )
    second_layer = FixedLayerData(
        sections=[FixedLayerSection(id="fresher", title="Fresher", content="fresher fixed")]
    )
    builder = FakeBuilder()
    agent = object.__new__(RPGGameAgent)
    agent._session_id = "s1"
    agent._builder = builder
    agent._fixed_layer = FixedLayerData()
    agent._assemble_fixed_layer = MagicMock(side_effect=[first_layer, second_layer])
    agent._refresh_sub_agent_contexts = MagicMock()
    agent._session = SimpleNamespace(
        history=[],
        context_history=lambda: SimpleNamespace(
            messages=(),
            filtered_message_count=0,
        ),
    )
    agent._status_mgr = None
    agent._scene_tracker = None
    agent._rp_module_registry = None

    first_ctx = agent._build_ctx_for_inspection("preview")
    second_ctx = agent._build_ctx_for_inspection("preview")

    assert agent._assemble_fixed_layer.call_count == 2
    assert agent._refresh_sub_agent_contexts.call_count == 2
    assert agent._fixed_layer is second_layer
    assert builder.fixed_layer is second_layer
    assert first_ctx.fixed_layer is first_layer
    assert second_ctx.fixed_layer is second_layer
    assert second_ctx.hot_history.messages[-1].content == "preview"


@pytest.mark.asyncio
async def test_ensure_initialized_populates_model_from_provider(monkeypatch):
    class FakeCoreRPContractContributor:
        name = "core"

        def __init__(self, _world_name: str) -> None:
            self.sections = []

        def get_fixed_contribution(self):
            from rpg_core.context.fixed_layer import FixedLayerContribution

            return FixedLayerContribution(sections=self.sections)

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
        def get_provider(self, _biz_key, overrides=None, *, provider_key=None):  # noqa: ANN001
            assert overrides == ProviderOverrides()
            assert provider_key == "main_chat"
            return FakeProvider()

    fake_watcher = FakeWatcher()
    def fake_create_task(coro):
        coro.close()
        return MagicMock()

    _patch_story_prompt_contributor(monkeypatch)
    monkeypatch.setattr(agent_module, "CoreRPContractContributor", FakeCoreRPContractContributor)
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
    agent._provider_overrides = ProviderOverrides()
    agent._main_llm_selection_service = SimpleNamespace(
        resolve_session=lambda _session_id: SimpleNamespace(
            effective_provider_key="main_chat",
            effective_source="config",
        )
    )
    agent._main_llm_selection = None
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
