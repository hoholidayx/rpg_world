"""RPGGameAgent — orchestrates history, 5-layer context build, and LLM call."""

from __future__ import annotations

import asyncio
import json
import time as _time
from asyncio import Future
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.agent_types import (
    AgentStreamEvent,
    QueueItem,
    QueueKind,
    StreamEventKind,
    TurnStats,
    _StreamSentinel,
)
from rpg_core.agent.command import CommandResult
from rpg_core.agent.command import CommandDispatcher
from rpg_core.agent.loop import AgentReply, ToolCallRecord, run_chat_loop, run_chat_loop_stream
from rpg_core.agent.sub_agents import (
    MemorySubAgent,
    StatusSubAgent,
    SubAgentContext,
)
from rpg_core.utils.tokenizer import TiktokenTokenCounter, TokenCounter
from rpg_core.agent.tools import (
    BaseTool,
    GrepTool,
    ListFilesTool,
    ReadFileTool,
    ToolRegistry,
    WriteFileTool,
)
from rpg_core.context import RPGContextBuilder
from rpg_core.context.fixed_layer import FixedLayerAssembler
from rpg_core.context.fixed_layer.contributors import (
    CharacterFixedLayerContributor,
    CoreRPContractContributor,
    LorebookFixedLayerContributor,
    StaticFixedLayerContributor,
    TextOutputFormatFixedLayerContributor,
)
from rpg_core.context.inspector import ContextInspector
from rpg_core.context.rpg_context import FixedLayerData, Role, Message
from llm_service.base_provider import LLMProvider
from llm_service.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_MEMORY_SUB_AGENT_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
)
from rpg_core.scene import SceneTracker
from rpg_core.session import SessionManager
from rpg_core.settings import settings
from rpg_core.utils.watcher import get_watcher
from rpg_core.summary.compressor import SummaryCompressor
from llm_service.manager import LLMManager, ProviderOverrides

if TYPE_CHECKING:
    from rpg_core.character.manager import CharacterManager
    from rpg_core.agent.command import CommandDef
    from rpg_core.lorebook.manager import LorebookManager
    from rpg_core.rp_modules import RPModuleRegistry
    from rp_memory.memory_manager import MemoryManager
    from rpg_core.status.manager import StatusManager

_TAG = "[MainAgent]"


class RPGGameAgent:
    """Standalone RPG agent.

    Owns the full lifecycle:
      1. RPG context (builder + managers + stores from ``build_rpg_context``)
      2. Conversation history (in-memory)
      3. OpenAI provider

    Usage::

        agent = RPGGameAgent()
        reply = await agent.send("look around the room")
        print(reply)
    """

    def __init__(
        self,
        session_id: str = "default",
        world_name: str = "Nanobot Realm",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        history_enabled: bool = True,
        tools: list[BaseTool] | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._session_id = session_id
        self._world_name = world_name
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider_overrides = ProviderOverrides(
            openai_model=model,
            openai_api_key=api_key,
            openai_base_url=base_url,
            openai_max_tokens=max_tokens,
            openai_temperature=temperature,
        )
        self._history_enabled = history_enabled
        self._extra_tools = tools or []
        self._token_counter = token_counter or TiktokenTokenCounter()

        self._initialized: bool = False
        self._builder: RPGContextBuilder | None = None
        self._character_mgr: CharacterManager | None = None
        self._lorebook_mgr: LorebookManager | None = None
        self._status_mgr: StatusManager | None = None
        self._scene_tracker: SceneTracker | None = None
        self._provider: LLMProvider | None = None
        self._fixed_layer = FixedLayerData(world_name=self._world_name)
        self._session = SessionManager(
            session_id=self._session_id,
            history_enabled=self._history_enabled,
        )
        self._tool_registry: ToolRegistry | None = None
        self._last_tool_records: list[ToolCallRecord] | None = None
        self._status_sub_agent: StatusSubAgent | None = None
        self._memory_sub_agent: MemorySubAgent | None = None
        self._compressor: SummaryCompressor | None = None
        self._cmd_dispatcher: CommandDispatcher | None = None
        self._rp_module_registry: RPModuleRegistry | None = None
        self._memory_manager: MemoryManager | None = None
        self._rpg_ctx: dict[str, object] = {}
        self._init_lock: asyncio.Lock | None = None

        # 会话确定后立即初始化 RPG context managers/stores（同步，不等第一句消息）
        self._refresh_rpg_context()

        # 消息队列（初始化时创建，_ensure_initialized 末尾启动消费者）
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._consumer_task: asyncio.Task | None = None

    def _create_future(self) -> asyncio.Future:
        """在当前运行中的事件循环里创建 Future。

        统一收口，避免多个入口各自使用过时的 ``get_event_loop()``。
        """
        return asyncio.get_running_loop().create_future()

    async def _emit_stream_error(self, event_queue: asyncio.Queue, error: BaseException) -> None:
        """把流式失败转换成可消费的 ERROR 事件并结束队列。"""
        await event_queue.put(AgentStreamEvent(
            kind=StreamEventKind.ERROR,
            content=str(error),
        ))
        await event_queue.put(_StreamSentinel())

    # ── 消息队列消费者 ─────────────────────────────────────────────────

    async def _queue_consumer(self) -> None:
        """后台消费者——逐个处理消息队列中的工作项。

        所有 ``send()`` / ``send_stream()`` / 命令都经过此消费者串行执行。
        ``_send_stream_impl`` 内部已捕获异常并通过 event_queue 传播，
        此处的异常捕获仅作为安全网。
        """
        while True:
            item: QueueItem = await self._queue.get()
            logger.debug(_TAG + " consumer processing: kind={}, input={!r:.60}", item.kind, item.user_input)
            try:
                match item.kind:
                    case QueueKind.SEND:
                        result = await self._send_impl(item.user_input)
                        item.future.set_result(result)
                    case QueueKind.SEND_STREAM:
                        await self._send_stream_impl(item.user_input, item.event_queue)
                        item.future.set_result(None)
                    case QueueKind.COMMAND:
                        cmd_result = await self._cmd_dispatcher.dispatch(item.user_input)
                        item.future.set_result(cmd_result)
                    case QueueKind.TRUNCATE_HISTORY:
                        if item.turn_id is None:
                            raise ValueError("turn_id is required")
                        result = self._truncate_history_from_turn_impl(item.turn_id)
                        item.future.set_result(result)
            except Exception as e:
                logger.warning(_TAG + " consumer error on kind={}: {}", item.kind, e)
                if item.kind == QueueKind.SEND_STREAM and item.event_queue is not None:
                    await self._emit_stream_error(item.event_queue, e)
                    if not item.future.done():
                        item.future.set_result(None)
                elif not item.future.done():
                    item.future.set_exception(e)
            finally:
                self._queue.task_done()

    # ── public API ─────────────────────────────────────────────────────

    async def send(self, user_input: str) -> AgentReply:
        """Send user text through the message queue and return a structured ``AgentReply``.

        If the agent is busy processing a previous message, this call waits
        in the queue until the agent is free.  The actual processing logic
        is in ``_send_impl()``.

        Usage is identical to the old ``send()`` — no caller changes needed.
        """
        await self._ensure_initialized()
        future: Future[AgentReply] = self._create_future()
        await self._queue.put(QueueItem(kind=QueueKind.SEND, user_input=user_input, future=future))
        logger.debug(_TAG + " send() enqueued: input={!r:.60}", user_input)
        return await future

    async def _send_impl(self, user_input: str) -> AgentReply:
        """Internal send implementation — runs inside the queue consumer.

        May involve multiple LLM round-trips when tool calls are needed
        (the chat loop).  The 5-layer context is built once; subsequent
        iterations append raw assistant/tool messages.

        The user message in session history includes the ``[scene]``
        context so that MemorySubAgent can see scene timeline during
        summarization (it filters ``role == "system"`` messages).
        """

        # ── 斜杠命令分发（不走 LLM） ─────────────────────────────────
        if self._cmd_dispatcher and self._cmd_dispatcher.is_command(user_input):
            cmd_result = await self._cmd_dispatcher.dispatch(user_input)
            if cmd_result.handled:
                _turn_stats = TurnStats(started_at=_time.monotonic())
                _turn_stats.finished_at = _time.monotonic()
                return AgentReply(
                    text=cmd_result.reply,
                    stats=_turn_stats,
                )

        role_guard_reply = self._player_character_guard_reply()
        if role_guard_reply:
            logger.info(
                _TAG + " blocked send because player character is invalid: session_id={}",
                self._session_id,
            )
            _turn_stats = TurnStats(started_at=_time.monotonic())
            _turn_stats.finished_at = _time.monotonic()
            return AgentReply(text=role_guard_reply, stats=_turn_stats)

        # ── TurnStats 聚合器（追踪本轮所有 LLM 调用） ──────────────
        self._session.validate_loaded_turn_metadata(label="history")
        turn_stats = TurnStats(started_at=_time.monotonic())
        turn_id = self._session.begin_turn()

        try:
            # ── 状态表预更新（~1-2K tokens，避免主 loop round-trip） ──────
            status_records = None
            if self._status_sub_agent and self._scene_tracker:
                scene_ctx_before = self._scene_tracker.get_context()
                sub_result = await self._status_sub_agent.update(
                    history=self._session.history,
                    state_context=scene_ctx_before,
                    user_input=user_input,
                    turn_stats=turn_stats,
                )
                if sub_result.updated:
                    logger.info(
                        _TAG + " StatusSubAgent updated scene via {}",
                        [r["tool_name"] for r in sub_result.records],
                    )
                    status_records = sub_result.records

            # Build scene context and embed into stored user message
            scene_ctx = self._scene_tracker.get_context() if self._scene_tracker else None
            stored_input = self._compose_stored_user_input(scene_ctx, user_input)

            self._session.append(Role.USER, stored_input, turn_id=turn_id)

            # ── 记忆检索 ────────────────────────────────────────────────
            if self._memory_manager:
                try:
                    self._memory_manager.recall(user_input)
                except Exception as exc:
                    logger.warning(_TAG + " memory recall failed: {}", exc)

            # ── 剧情记忆自动触发（内部判断条件，后台异步执行） ──────────
            if self._memory_sub_agent:
                await self._memory_sub_agent.maybe_auto_extract(self._session)

            # ── 自动压缩 ──────────────────────────────────────────────────
            if self._compressor:
                try:
                    compress_result = await self._compressor.maybe_compress(
                        self._session
                    )
                    if compress_result.triggered:
                        logger.info(
                            _TAG + " auto-compressed: {} turns, {} batches",
                            compress_result.user_rounds_compressed,
                            len(compress_result.batch_files or []),
                        )
                except Exception as exc:
                    logger.warning(_TAG + " auto-compress failed: {}", exc)

            messages = self._build_transformed_context()
            if settings.verbose_logging:
                sys_msgs = sum(1 for m in messages if m.is_system())
                user_msgs = sum(1 for m in messages if m.is_user())
                asst_msgs = sum(1 for m in messages if m.is_assistant())
                total_chars = sum(len(m.content) for m in messages)
                logger.debug(
                    _TAG + " context messages: {} total (sys={}, user={}, asst={}) chars={}",
                    len(messages), sys_msgs, user_msgs, asst_msgs, total_chars,
                )

            schemas = self._tool_registry.get_openai_schemas() if self._tool_registry else None

            reply_text, records = await run_chat_loop(
                provider=self._provider,
                tool_registry=self._tool_registry,
                messages=messages,
                schemas=schemas,
                turn_stats=turn_stats,
            )
            self._last_tool_records = records

            turn_stats.finished_at = _time.monotonic()

            # ── 日志摘要 ────────────────────────────────────────────────
            if turn_stats.calls:
                logger.info(
                    _TAG + " turn stats: {}",
                    turn_stats.summary(),
                )

            # ── 构建 AgentReply ──────────────────────────────────────────
            if settings.include_tool_records:
                result = AgentReply(
                    text=reply_text,
                    tool_records=records or None,
                    status_sub_agent_records=status_records,
                    stats=turn_stats,
                )
            else:
                result = AgentReply(
                    text=reply_text,
                    status_sub_agent_records=status_records,
                    stats=turn_stats,
                )

            self._session.append(Role.ASSISTANT, reply_text, turn_id=turn_id)
            return result
        finally:
            self._session.end_turn(turn_id)

    async def send_stream(self, user_input: str) -> AsyncIterator[AgentStreamEvent]:
        """Streaming variant of ``send()``, goes through the message queue.

        Enqueues the request and streams events from a per-request event queue
        so that the consumer's output is delivered incrementally to the caller.

        Usage is identical to the old ``send_stream()`` — no caller changes needed.
        """
        await self._ensure_initialized()
        event_queue: asyncio.Queue[AgentStreamEvent | BaseException | _StreamSentinel] = asyncio.Queue()
        future: Future[None] = self._create_future()
        await self._queue.put(QueueItem(
            kind=QueueKind.SEND_STREAM, user_input=user_input, future=future, event_queue=event_queue,
        ))
        logger.debug(_TAG + " send_stream() enqueued: input={!r:.60}", user_input)
        while True:
            item = await event_queue.get()
            if isinstance(item, _StreamSentinel):
                break
            if isinstance(item, BaseException):
                raise item
            yield item
        # 如果消费者侧有未预期的异常，在此处传播
        if future.done() and future.exception():
            raise future.exception()

    async def _send_stream_impl(self, user_input: str, event_queue: asyncio.Queue) -> None:
        """Internal send_stream implementation — runs inside the queue consumer.

        Pushes ``AgentStreamEvent`` objects into *event_queue* instead of
        yielding them directly.  Exceptions are also pushed into the queue
        so the caller can re-raise them.
        """

        # ── 斜杠命令分发（不走 LLM） ─────────────────────────────────
        if self._cmd_dispatcher and self._cmd_dispatcher.is_command(user_input):
            cmd_result = await self._cmd_dispatcher.dispatch(user_input)
            if cmd_result.handled:
                if cmd_result.reply:
                    await event_queue.put(AgentStreamEvent(
                        kind=StreamEventKind.TEXT,
                        content=cmd_result.reply,
                        model=self._model,
                    ))
                await event_queue.put(AgentStreamEvent(
                    kind=StreamEventKind.DONE,
                    content=cmd_result.reply,
                    model=self._model,
                ))
                await event_queue.put(_StreamSentinel())
                return

        role_guard_reply = self._player_character_guard_reply()
        if role_guard_reply:
            logger.info(
                _TAG + " blocked stream because player character is invalid: session_id={}",
                self._session_id,
            )
            await event_queue.put(AgentStreamEvent(
                kind=StreamEventKind.TEXT,
                content=role_guard_reply,
                model=self._model,
            ))
            await event_queue.put(AgentStreamEvent(
                kind=StreamEventKind.DONE,
                content=role_guard_reply,
                model=self._model,
            ))
            await event_queue.put(_StreamSentinel())
            return

        # ── TurnStats 聚合器 ───────────────────────────────────────
        self._session.validate_loaded_turn_metadata(label="history")
        turn_stats = TurnStats(started_at=_time.monotonic())
        turn_id = self._session.begin_turn()

        try:
            # ── 状态表预更新（~1-2K tokens，避免主 loop round-trip） ────
            status_records = None
            if self._status_sub_agent and self._scene_tracker:
                scene_ctx_before = self._scene_tracker.get_context()
                sub_result = await self._status_sub_agent.update(
                    history=self._session.history,
                    state_context=scene_ctx_before,
                    user_input=user_input,
                    turn_stats=turn_stats,
                )
                if sub_result.updated:
                    logger.info(
                        _TAG + " StatusSubAgent updated scene via {}",
                        [r["tool_name"] for r in sub_result.records],
                    )
                    status_records = sub_result.records
                    # 将 sub-agent 工具调用作为流事件发射，让 CLI 实时显示
                    for r in status_records:
                        await event_queue.put(AgentStreamEvent(
                            kind=StreamEventKind.TOOL_CALL,
                            tool_name=r["tool_name"],
                            tool_arguments=str(r.get("arguments", "")),
                            content="",
                        ))
                        await event_queue.put(AgentStreamEvent(
                            kind=StreamEventKind.TOOL_RESULT,
                            tool_name=r["tool_name"],
                            tool_result=str(r.get("result", "")),
                            tool_result_preview=str(r.get("result", ""))[:200],
                        ))

            # ── Build scene context and embed into stored user message ──
            scene_ctx = self._scene_tracker.get_context() if self._scene_tracker else None
            stored_input = self._compose_stored_user_input(scene_ctx, user_input)

            self._session.append(Role.USER, stored_input, turn_id=turn_id)

            # ── 记忆检索 ────────────────────────────────────────────────
            if self._memory_manager:
                try:
                    self._memory_manager.recall(user_input)
                except Exception as exc:
                    logger.warning(_TAG + " memory recall failed: {}", exc)

            # ── 剧情记忆自动触发（内部判断条件，后台异步执行） ──────────
            if self._memory_sub_agent:
                await self._memory_sub_agent.maybe_auto_extract(self._session)

            # ── 自动压缩 ──────────────────────────────────────────────────
            if self._compressor:
                try:
                    compress_result = await self._compressor.maybe_compress(
                        self._session
                    )
                    if compress_result.triggered:
                        logger.info(
                            _TAG + " auto-compressed: {} turns, {} batches",
                            compress_result.user_rounds_compressed,
                            len(compress_result.batch_files or []),
                        )
                except Exception as exc:
                    logger.warning(_TAG + " auto-compress failed: {}", exc)

            messages = self._build_transformed_context()
            schemas = self._tool_registry.get_openai_schemas() if self._tool_registry else None

            # ── Stream loop ────────────────────────────────────────────
            final_content = ""
            final_event: AgentStreamEvent | None = None

            try:
                async for event in run_chat_loop_stream(
                        provider=self._provider,
                        tool_registry=self._tool_registry,
                        messages=messages,
                        schemas=schemas,
                        turn_stats=turn_stats,
                ):
                    if event.kind == StreamEventKind.DONE:
                        final_content = event.content
                        final_event = event
                    else:
                        await event_queue.put(event)
            except Exception as exc:
                logger.error("{} send_stream error: {}", _TAG, exc)
                await event_queue.put(AgentStreamEvent(
                    kind=StreamEventKind.ERROR,
                    content=str(exc),
                ))
                await event_queue.put(_StreamSentinel())
                return

            # ── Agent-level cleanup（流结束后执行） ────────────────────
            turn_stats.finished_at = _time.monotonic()

            if settings.verbose_logging and turn_stats.calls:
                logger.info(
                    _TAG + " turn stats: {}",
                    turn_stats.summary(),
                )

            # Only persist to history if we got valid content
            if final_content:
                self._session.append(Role.ASSISTANT, final_content, turn_id=turn_id)

            # ── 构建最终的 DONE 事件（含完整元数据） ──────────────────
            # Compute aggregate usage across all LLM calls (main loop + sub-agents)
            from rpg_core.agent.agent_types import LLMUsage

            total_pt = turn_stats.total_prompt_tokens
            total_ct = turn_stats.total_completion_tokens
            total_cached = turn_stats.total_cached_tokens
            total_missed = sum(
                c.usage.prompt_cache_miss_tokens for c in turn_stats.calls if c.usage
            )
            aggregate_usage = LLMUsage(
                prompt_tokens=total_pt,
                completion_tokens=total_ct,
                total_tokens=total_pt + total_ct,
                prompt_tokens_details={"cached_tokens": total_cached} if total_cached else None,
                prompt_cache_hit_tokens=total_cached,
                prompt_cache_miss_tokens=total_missed,
            )

            if final_event is not None:
                final_event.duration_ms = turn_stats.total_duration_ms
                final_event.usage = aggregate_usage
                final_event.stats = turn_stats
                await event_queue.put(final_event)
            else:
                await event_queue.put(AgentStreamEvent(
                    kind=StreamEventKind.DONE,
                    content=final_content,
                    usage=aggregate_usage,
                    duration_ms=turn_stats.total_duration_ms,
                    model=self._model,
                ))
            await event_queue.put(_StreamSentinel())
        finally:
            self._session.end_turn(turn_id)

    async def execute_command(self, command: str) -> CommandResult:
        """将斜杠命令入队执行，返回执行结果。

        通过消息队列串行化，避免与正在处理的 ``send()`` 竞态。
        供 ``/chat/command`` API 端点使用。
        """
        await self._ensure_initialized()
        future: Future[CommandResult] = self._create_future()
        await self._queue.put(QueueItem(kind=QueueKind.COMMAND, user_input=command, future=future))
        logger.debug(_TAG + " execute_command() enqueued: cmd={!r:.60}", command)
        return await future

    def list_commands(self) -> list["CommandDef"]:
        """返回当前 agent 可用的全部斜杠命令定义。"""
        if self._cmd_dispatcher is None:
            return []
        return self._cmd_dispatcher.list_commands()

    def render_role_bind_prompt(self, *, error: str = "") -> str:
        from rpg_data.services import get_data_service_gateway

        return get_data_service_gateway().session_roles.render_role_bind_prompt(
            self._session_id,
            error=error,
        )

    def bind_player_character_by_index(self, index: int):
        from rpg_data.services import get_data_service_gateway

        logger.info(_TAG + " binding player character by index: session_id={}, index={}", self._session_id, index)
        result = get_data_service_gateway().session_roles.bind_by_index(self._session_id, int(index))
        self._session.load()
        logger.info(
            _TAG + " player character binding loaded history: session_id={}, index={}, first_message_appended={}, history_len={}",
            self._session_id,
            index,
            bool(result.first_message),
            len(self._session.history),
        )
        return result

    def _player_character_guard_reply(self) -> str:
        from rpg_data import models
        from rpg_data.services import get_data_service_gateway

        session_id = str(getattr(self, "_session_id", "") or "")
        if not session_id:
            return ""
        service = get_data_service_gateway().session_roles
        try:
            state = service.get_state(session_id)
        except FileNotFoundError:
            logger.warning(_TAG + " player character guard skipped missing session: session_id={}", session_id)
            return ""
        if state.status == models.PLAYER_CHARACTER_STATUS_BOUND:
            return ""
        logger.info(
            _TAG + " player character guard requires binding: session_id={}, status={}",
            session_id,
            state.status,
        )
        return service.render_role_bind_prompt(session_id)

    @property
    def history(self) -> list[Message]:
        """Read-only view of the raw conversation history (before RPG transform)."""
        return self._session.history

    async def reload_history(self) -> None:
        """Reload mutable SQL history into this cached agent."""
        await self._ensure_initialized()
        await self._queue.join()
        self._session.load()

    async def truncate_history_from_turn(self, turn_id: int) -> dict[str, object]:
        """Queue a history truncation behind any active send/stream work."""
        await self._ensure_initialized()
        future: Future[dict[str, object]] = self._create_future()
        await self._queue.put(
            QueueItem(
                kind=QueueKind.TRUNCATE_HISTORY,
                user_input="",
                future=future,
                turn_id=int(turn_id),
            )
        )
        logger.debug(
            _TAG + " truncate_history_from_turn() enqueued: session_id={}, turn_id={}",
            self._session_id,
            turn_id,
        )
        return await future

    def _truncate_history_from_turn_impl(self, turn_id: int) -> dict[str, object]:
        boundary_turn = int(turn_id)
        if boundary_turn <= 0:
            raise ValueError("turn_id must be positive")
        if self._session.first_user_message_for_turn(boundary_turn) is None:
            logger.warning(
                _TAG + " truncate rejected: user message not found, session_id={}, turn_id={}",
                self._session_id,
                boundary_turn,
            )
            raise ValueError(f"user message not found for turn: {boundary_turn}")

        before_count = len(self._session.history)
        logger.info(
            _TAG + " truncate starting: session_id={}, turn_id={}, history_count={}",
            self._session_id,
            boundary_turn,
            before_count,
        )
        try:
            removed = self._session.truncate_from_turn(boundary_turn)
        except Exception as exc:
            remaining_rows = self._history_rows()
            if any(int(row.turn_id) == boundary_turn for row in remaining_rows):
                raise
            logger.warning(
                _TAG + " truncate persisted but agent reload failed: session_id={}, turn_id={}, error={}",
                self._session_id,
                boundary_turn,
                exc,
            )
            return {
                "status": "truncated",
                "session_id": self._session_id,
                "turn_id": boundary_turn,
                "removed": max(0, before_count - len(remaining_rows)),
                "agent_sync_status": "failed",
                "agent_sync_error": str(exc),
            }

        logger.info(
            _TAG + " truncate completed: session_id={}, turn_id={}, removed={}, remaining_count={}",
            self._session_id,
            boundary_turn,
            removed,
            len(self._session.history),
        )
        return {
            "status": "truncated",
            "session_id": self._session_id,
            "turn_id": boundary_turn,
            "removed": removed,
            "agent_sync_status": "synced",
        }

    def _history_rows(self):
        from rpg_data.services import get_data_service_gateway

        return get_data_service_gateway().messages.list(self._session_id)

    async def delete_message(self, message_id: int) -> Message:
        """Delete one history message and reload this cached agent."""
        await self._ensure_initialized()
        await self._queue.join()
        return self._session.delete_message(message_id)

    @property
    def last_tool_records(self) -> list[ToolCallRecord] | None:
        """Tool-call records from the most recent ``send()``.

        ``None`` if no tool calls were made.  Useful for displaying
        intermediate tool usage in UIs without persisting them to history.
        """
        return self._last_tool_records

    def clear_history(self) -> None:
        """清空对话历史（RPG 数据保留不动）。

        Also clears the mutable rpg_data message table so the next session
        starts fresh. Cold backup records are append-only.
        """
        if self._initialized:
            self._session.clear()

    async def reload_rpg_context(self) -> None:
        """重新构建 RPG context 管理器，拾取文件变更。

        复用 ``_refresh_rpg_context()`` 与初始化流程一致的逻辑。
        """
        if not self._initialized:
            return
        self._refresh_rpg_context()
        self._register_rp_module_commands()
        self._setup_tool_registry()

    async def switch_session(self, session_id: str) -> None:
        """原地切换到指定会话，不退出 REPL/Agent。

        依次执行：
        1. 更新 session_id
        2. 重建所有 manager/store（build_rpg_context 接收新 session_id）
        3. 清空并重载历史
        4. 重建工具注册表

        session 未变时直接返回，避免每轮消息都重建 MemoryManager。
        """
        if self._session_id == session_id:
            return
        self._session_id = session_id
        self._refresh_rpg_context()
        if self._memory_manager:
            self._memory_manager.init()
        get_watcher().start()
        self._session.switch_to(session_id)
        self._register_rp_module_commands()
        self._setup_tool_registry()
        logger.info("[MainAgent] switched to session: {}", session_id)

    # ── context inspection (no LLM call) ─────────────────────────────

    async def get_context_info(self, user_input: str = "") -> list["LayerInfo"]:
        """Build the full 5-layer context and return structured layer metadata.

        Uses the current ``_history`` and *user_input* (optional) to assemble
        the context **without** sending it to the LLM.  ``_history`` is not
        modified.

        Returns a list of ``LayerInfo``, one per layer, with token counts
        estimated using the agent's ``_token_counter``.
        """

        await self._ensure_initialized()
        ctx = self._build_ctx_for_inspection(user_input)
        return ContextInspector(
            ctx,
            self._token_counter,
            hot_history_rounds=self._builder.config.hot_history_rounds,
        ).layer_summary()

    async def get_context_markdown(self, user_input: str = "") -> str:
        """Build the full 5-layer context and return a Markdown-formatted table.

        Convenience wrapper around ``get_context_info()`` that renders the
        result as a Markdown table string suitable for CLI display or tool
        output.
        """
        await self._ensure_initialized()
        ctx = self._build_ctx_for_inspection(user_input)
        return ContextInspector(
            ctx,
            self._token_counter,
            hot_history_rounds=self._builder.config.hot_history_rounds,
        ).to_markdown()

    async def get_context_payload(self, user_input: str = "") -> dict[str, object]:
        """Build the full 5-layer context and return a JSON-ready payload."""
        await self._ensure_initialized()
        ctx = self._build_ctx_for_inspection(user_input)
        return ContextInspector(
            ctx,
            self._token_counter,
            hot_history_rounds=self._builder.config.hot_history_rounds,
        ).to_payload(session_id=self._session_id)

    async def get_context_json(self, user_input: str = "") -> str:
        """Build the full 5-layer context and return formatted JSON text."""
        payload = await self.get_context_payload(user_input)
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_ctx_for_inspection(self, user_input: str = "") -> "RPGContext":
        """Build context for inspection (no _history mutation, no LLM call)."""
        from rpg_core.context.rpg_context import RPGContext

        self._refresh_fixed_layer_snapshot()

        # Build scene context same way as send()
        scene_ctx = self._scene_tracker.get_context() if self._scene_tracker else None

        test_messages: list[Message] = list(self._session.history)
        if user_input or scene_ctx:
            stored_input = self._compose_stored_user_input(scene_ctx, user_input)
            test_messages.append(Message(role=Role.USER, content=stored_input))
        elif not test_messages:
            test_messages.append(Message(role=Role.USER, content="(no input)"))

        ctx: RPGContext = self._builder.build(
            fixed_layer=self._fixed_layer,
            messages=test_messages,
            status_mgr=self._status_mgr,
            scene_tracker=self._scene_tracker,
            rp_module_sections=self._get_rp_module_runtime_sections(user_input=user_input),
        )
        return ctx

    @staticmethod
    def _compose_stored_user_input(scene_ctx: str | None, user_input: str) -> str:
        if scene_ctx and user_input:
            return f"{scene_ctx}\n{user_input}"
        return scene_ctx or user_input

    # ── internals — context & tools ────────────────────────────────────

    def _refresh_rpg_context(self) -> None:
        """构建/刷新 RPG context 管理器（初始化与 reload 共用）。

        重新执行 ``_build_rpg_context()`` 并更新 manager 引用，
        然后刷新 SubAgentContext。不涉及 provider / history / tools 等一次性初始化。
        """
        self._rpg_ctx = _build_rpg_context(
            world_name=self._world_name,
            session_id=self._session_id,
        )
        self._builder = self._rpg_ctx["builder"]
        self._character_mgr = self._rpg_ctx["character_mgr"]
        self._lorebook_mgr = self._rpg_ctx["lorebook_mgr"]
        self._status_mgr = self._rpg_ctx["status_mgr"]
        self._scene_tracker = self._rpg_ctx.get("scene_tracker")
        self._memory_manager = self._rpg_ctx.get("memory_manager")

        self._refresh_sub_agent_contexts(refresh_status_tool_providers=True)
        if self._rp_module_registry is not None:
            self._setup_rp_module_registry()
        else:
            self._fixed_layer = self._assemble_fixed_layer()

    def _refresh_sub_agent_contexts(self, *, refresh_status_tool_providers: bool = False) -> None:
        """Refresh sub-agent fixed-layer prompts from current character/lorebook managers."""
        if self._status_sub_agent is not None:
            _sub_ctx_status = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
            self._status_sub_agent.bind_context(_sub_ctx_status)
            # Session switches rebuild SceneTracker; refresh tool references only on full context reload.
            if refresh_status_tool_providers and self._scene_tracker is not None:
                self._status_sub_agent._tool_providers.clear()
                self._status_sub_agent.add_tool_provider(self._scene_tracker)
        if self._memory_sub_agent is not None:
            _sub_ctx_memory = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
            self._memory_sub_agent.bind_context(_sub_ctx_memory)

    def _assemble_fixed_layer(self) -> FixedLayerData:
        builder = self._builder
        builder_config = getattr(builder, "config", None)
        enable_lorebook = getattr(builder_config, "enable_lorebook", True)
        enable_character = getattr(builder_config, "enable_character", True)
        assembler = FixedLayerAssembler(
            world_name=self._world_name,
            contributors=[
                CoreRPContractContributor(self._world_name),
                TextOutputFormatFixedLayerContributor(),
                LorebookFixedLayerContributor(
                    self._lorebook_mgr,
                    enabled=enable_lorebook,
                ),
                CharacterFixedLayerContributor(
                    self._character_mgr,
                    enabled=enable_character,
                ),
            ],
        )
        if self._rp_module_registry is not None:
            assembler = assembler.with_contributor(
                StaticFixedLayerContributor(self._rp_module_registry.get_fixed_sections())
            )
        return assembler.assemble()

    def _setup_rp_module_registry(self) -> None:
        """Build the session-scoped RP Module registry and fixed sections."""
        from rpg_core.rp_modules import RPModuleRegistry

        rp_settings = getattr(settings, "rp_module_settings", None)
        self._rp_module_registry = RPModuleRegistry(
            session_id=self._session_id,
            world_name=self._world_name,
            status_mgr=self._status_mgr,
            scene_tracker=self._scene_tracker,
            settings=rp_settings,
        )
        self._fixed_layer = self._assemble_fixed_layer()

    def _register_rp_module_commands(self) -> None:
        """Expose RP Module slash commands through the existing dispatcher."""
        dispatcher = getattr(self, "_cmd_dispatcher", None)
        registry = getattr(self, "_rp_module_registry", None)
        if dispatcher is None or registry is None:
            return
        if not hasattr(dispatcher, "register_builtin"):
            return
        for command in registry.get_commands():
            dispatcher.register_builtin(
                command.name,
                command.description,
                command.detail,
                command.handler,
            )

    def _get_rp_module_runtime_sections(self, user_input: str = ""):
        """Collect dynamic RP module sections. Dice MVP returns an empty list."""
        if self._rp_module_registry is None:
            return []
        from rpg_core.rp_modules.models import ModuleContextRequest

        return self._rp_module_registry.get_runtime_sections(
            ModuleContextRequest(session_id=self._session_id, user_input=user_input),
        )

    def _refresh_fixed_layer_snapshot(self) -> None:
        """Rebuild fixed-layer sections from the latest character/lorebook data."""
        self._fixed_layer = self._assemble_fixed_layer()
        self._refresh_sub_agent_contexts()

    def _build_transformed_context(self) -> list[Message]:
        """Build the 5-layer RPG context as Message objects."""
        self._refresh_fixed_layer_snapshot()
        ctx = self._builder.build(
            fixed_layer=self._fixed_layer,
            messages=self._session.history,
            status_mgr=self._status_mgr,
            scene_tracker=self._scene_tracker,
            rp_module_sections=self._get_rp_module_runtime_sections(),
        )
        return ctx.to_message_objects()

    def _setup_tool_registry(self) -> None:
        """Create and populate the ToolRegistry with built-in file tools."""
        from rpg_core.agent.tools.file_tools import FileToolSandbox
        from rpg_data.services import get_data_service_gateway

        session_root = get_data_service_gateway().catalog.get_session_runtime_dir(self._session_id)
        sandbox = FileToolSandbox(session_root=session_root)
        self._tool_registry = ToolRegistry()
        self._tool_registry.register_all([
            ListFilesTool(sandbox),
            ReadFileTool(sandbox),
            WriteFileTool(sandbox),
            GrepTool(sandbox),
        ])
        if self._scene_tracker:
            self._tool_registry.register_all(self._scene_tracker.get_tools())
        if self._rp_module_registry:
            self._tool_registry.register_all(self._rp_module_registry.get_tools())
        if self._extra_tools:
            self._tool_registry.register_all(self._extra_tools)

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        if self._init_lock is None:
            self._init_lock = asyncio.Lock()

        async with self._init_lock:
            if self._initialized:
                return

            self._setup_rp_module_registry()
            self._session.load()

            # ── MemoryManager 初始化（仅注册 FileWatcher） ─────────
            if self._memory_manager:
                self._memory_manager.init()

            provider_overrides = getattr(self, "_provider_overrides", None)
            manager = LLMManager.get()
            if provider_overrides is None:
                self._provider = manager.get_provider(AGENT_MAIN_BIZ_KEY)
            else:
                self._provider = manager.get_provider(
                    AGENT_MAIN_BIZ_KEY,
                    overrides=provider_overrides,
                )
            if self._model is None:
                self._model = self._provider.get_default_model()

            # ── StatusSubAgent ────────────────────────────────────────────
            status_cfg = settings.status_sub_agent_config
            self._status_sub_agent = StatusSubAgent(
                provider_biz_key=AGENT_STATUS_SUB_AGENT_BIZ_KEY,
                provider_overrides=provider_overrides,
                enabled=status_cfg.get("enabled", True),
            )
            if self._scene_tracker:
                self._status_sub_agent.add_tool_provider(self._scene_tracker)
            _status_ctx = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
            self._status_sub_agent.bind_context(_status_ctx)

            # ── MemorySubAgent ────────────────────────────────────────────
            memory_cfg = settings.memory_sub_agent_config
            self._memory_sub_agent = MemorySubAgent(
                provider_biz_key=AGENT_MEMORY_SUB_AGENT_BIZ_KEY,
                provider_overrides=provider_overrides,
                enabled=memory_cfg.get("enabled", True),
                summary_store=self._builder._summary_store if self._builder else None,
                story_store=self._builder._story_memory if self._builder else None,
                batch_store=self._builder._batch_summary_store if self._builder else None,
                max_window_rounds=settings.memory_keep_rounds,
            )
            _memory_ctx = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
            self._memory_sub_agent.bind_context(_memory_ctx)

            # ── SummaryCompressor ─────────────────────────────────────────
            self._compressor = SummaryCompressor(
                batch_store=self._builder._batch_summary_store if self._builder else None,
                memory_sub_agent=self._memory_sub_agent,
                enabled=settings.memory_compression_enabled,
                keep_recent_rounds=settings.memory_keep_rounds,
                compression_threshold=settings.memory_keep_rounds,
                compress_batch_size=settings.memory_compress_batch_size,
            )

            # ── CommandDispatcher ─────────────────────────────────────────
            self._cmd_dispatcher = CommandDispatcher(agent=self)
            self._cmd_dispatcher.register_default_builtins()
            self._register_rp_module_commands()

            # 子 Agent 命令
            if self._status_sub_agent is not None and self._status_sub_agent.enabled:
                self._cmd_dispatcher.register_sub_agent(self._status_sub_agent)
            if self._memory_sub_agent is not None and self._memory_sub_agent.enabled:
                self._cmd_dispatcher.register_sub_agent(self._memory_sub_agent)

            self._setup_tool_registry()

            # 启动文件监听（summary / memory store 会注册自己的 session 文件路径）
            get_watcher().start()

            # 启动消息队列消费者
            self._consumer_task = asyncio.create_task(self._queue_consumer())

            self._initialized = True


def _build_rpg_context(world_name: str, session_id: str) -> dict[str, object]:
    """Inline import of the factory to keep the top level free of side effects."""
    from rpg_core.context.factory import build_rpg_context

    return build_rpg_context(world_name=world_name, session_id=session_id)


def _build_sub_agent_context(
        character_mgr: CharacterManager | None,
        lorebook_mgr: LorebookManager | None,
) -> SubAgentContext:
    """从 Manager 读取已启用条目，构造 SubAgentContext。

    主 Agent 读 Manager 后直接传 data，SubAgentContext 不依赖 Manager 类型。
    """
    lorebook_entries: list[dict[str, object]] = []
    if lorebook_mgr is not None:
        try:
            lorebook_entries = lorebook_mgr.list_enabled_entries()
        except Exception:
            pass

    characters: list[dict[str, object]] = []
    if character_mgr is not None:
        try:
            characters = character_mgr.list_enabled_characters()
        except Exception:
            pass

    return SubAgentContext(
        lorebook_entries=lorebook_entries,
        characters=characters,
    )
