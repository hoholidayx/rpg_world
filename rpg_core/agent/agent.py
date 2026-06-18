"""RPGGameAgent — orchestrates history, 5-layer context build, and LLM call."""

from __future__ import annotations

import asyncio
import os
import time as _time
from asyncio import Future
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from rpg_world.rpg_core.agent.agent_types import (
    LLM_PROVIDER_LLAMA,
    LLM_PROVIDER_MODES,
    LLM_PROVIDER_OPENAI,
    LLM_PROVIDER_SHARED,
)
from rpg_world.rpg_core.agent.agent_types import (
    AgentStreamEvent,
    QueueItem,
    QueueKind,
    StreamEventKind,
    TurnStats,
    _StreamSentinel,
)
from rpg_world.rpg_core.agent.command import CommandResult
from rpg_world.rpg_core.agent.base_provider import LLMProvider
from rpg_world.rpg_core.agent.command import CommandDispatcher
from rpg_world.rpg_core.agent.loop import AgentReply, ToolCallRecord, run_chat_loop, run_chat_loop_stream
from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider
from rpg_world.rpg_core.agent.prompt import PromptManager
from rpg_world.rpg_core.agent.sub_agents import (
    MemorySubAgent,
    StatusSubAgent,
    SubAgentContext,
)
from rpg_world.rpg_core.agent.sub_agents.base import SubAgentProviderConfig
from rpg_world.rpg_core.utils.tokenizer import TiktokenTokenCounter, TokenCounter
from rpg_world.rpg_core.agent.tools import (
    BaseTool,
    GrepTool,
    ListFilesTool,
    ReadFileTool,
    ToolRegistry,
    WriteFileTool,
)
from rpg_world.rpg_core.context import RPGContextBuilder
from rpg_world.rpg_core.context.rpg_context import Role, Message
from rpg_world.rpg_core.scene import SceneTracker
from rpg_world.rpg_core.session import SessionManager
from rpg_world.rpg_core.settings import settings
from rpg_world.rpg_core.utils.path_utils import PACKAGE_ROOT
from rpg_world.rpg_core.utils.watcher import get_watcher
from rpg_world.rpg_core.summary.compressor import SummaryCompressor

if TYPE_CHECKING:
    from rpg_world.rpg_core.character.manager import CharacterManager
    from rpg_world.rpg_core.agent.command import CommandDef
    from rpg_world.rpg_core.lorebook.manager import LorebookManager
    from rpg_world.rpg_core.memory.memory_manager import MemoryManager
    from rpg_world.rpg_core.status.manager import StatusManager

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
            workspace: str = "",
            world_name: str = "Nanobot Realm",
            model: str = "gpt-4o",
            api_key: str | None = None,
            base_url: str | None = None,
            max_tokens: int | None = None,
            temperature: float | None = None,
            history_enabled: bool = True,
            tools: list[BaseTool] | None = None,
            token_counter: TokenCounter | None = None,
    ) -> None:
        self._session_id = session_id
        self._workspace = workspace
        self._world_name = world_name
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._temperature = temperature
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
        self._system_prompt: str = ""
        self._session = SessionManager(
            session_id=self._session_id,
            workspace=self._workspace,
            history_enabled=self._history_enabled,
        )
        self._tool_registry: ToolRegistry | None = None
        self._last_tool_records: list[ToolCallRecord] | None = None
        self._status_sub_agent: StatusSubAgent | None = None
        self._memory_sub_agent: MemorySubAgent | None = None
        self._compressor: SummaryCompressor | None = None
        self._cmd_dispatcher: CommandDispatcher | None = None
        self._memory_manager: MemoryManager | None = None
        self._rpg_ctx: dict[str, object] = {}

        # 会话确定后立即初始化 RPG context managers/stores（同步，不等第一句消息）
        self._refresh_rpg_context()

        # 消息队列（初始化时创建，_ensure_initialized 末尾启动消费者）
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._consumer_task: asyncio.Task | None = None

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
            except Exception as e:
                logger.warning(_TAG + " consumer error on kind={}: {}", item.kind, e)
                if not item.future.done():
                    item.future.set_exception(e)
            finally:
                self._queue.task_done()

    # ── public API ─────────────────────────────────────────────────────

    async def single_turn(self, user_input: str, record_history: bool = False) -> AgentReply:
        """One-shot message — send user text, get structured reply.

        Delegates to ``send()`` for the core logic, then rolls back
        ``_history`` so that no conversation state persists across
        calls.  Each invocation is stateless while sharing the same
        internal send path.

        When *record_history* is ``False`` (default), no history is
        loaded from or saved to disk.  Pass ``record_history=True`` to
        persist this single turn to the JSONL file for the session.
        """
        cp = self._session.checkpoint()
        original = self._session.history_enabled
        self._session.set_history_enabled(record_history)
        try:
            reply = await self.send(user_input)
        finally:
            self._session.set_history_enabled(original)
            self._session.rollback(cp)
        return reply

    async def send(self, user_input: str) -> AgentReply:
        """Send user text through the message queue and return a structured ``AgentReply``.

        If the agent is busy processing a previous message, this call waits
        in the queue until the agent is free.  The actual processing logic
        is in ``_send_impl()``.

        Usage is identical to the old ``send()`` — no caller changes needed.
        """
        await self._ensure_initialized()
        future: Future[AgentReply] = asyncio.get_event_loop().create_future()
        await self._queue.put(QueueItem(kind=QueueKind.SEND, user_input=user_input, future=future))
        logger.debug(_TAG + " send() enqueued: input={!r:.60}", user_input)
        return await future

    async def _send_impl(self, user_input: str) -> AgentReply:
        """Internal send implementation — runs inside the queue consumer.

        May involve multiple LLM round-trips when tool calls are needed
        (the chat loop).  The 5-layer context is built once; subsequent
        iterations append raw assistant/tool messages.

        The user message in ``_history`` / JSONL includes the ``[scene]``
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

        # ── TurnStats 聚合器（追踪本轮所有 LLM 调用） ──────────────
        turn_stats = TurnStats(started_at=_time.monotonic())

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
        if scene_ctx:
            stored_input = f"{scene_ctx}\n\n{user_input}"
        else:
            stored_input = user_input

        self._session.append(Role.USER, stored_input)

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
                    self._session.history
                )
                if compress_result.triggered:
                    logger.info(
                        _TAG + " auto-compressed: {} rounds, {} batches",
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

        self._session.append(Role.ASSISTANT, reply_text)
        return result

    async def send_stream(self, user_input: str) -> AsyncIterator[AgentStreamEvent]:
        """Streaming variant of ``send()``, goes through the message queue.

        Enqueues the request and streams events from a per-request event queue
        so that the consumer's output is delivered incrementally to the caller.

        Usage is identical to the old ``send_stream()`` — no caller changes needed.
        """
        await self._ensure_initialized()
        event_queue: asyncio.Queue[AgentStreamEvent | BaseException | _StreamSentinel] = asyncio.Queue()
        future: Future[None] = asyncio.get_event_loop().create_future()
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
                await event_queue.put(AgentStreamEvent(
                    kind=StreamEventKind.DONE,
                    content=cmd_result.reply,
                    model=self._model,
                ))
                await event_queue.put(_StreamSentinel())
                return

        # ── TurnStats 聚合器 ───────────────────────────────────────
        turn_stats = TurnStats(started_at=_time.monotonic())

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
        if scene_ctx:
            stored_input = f"{scene_ctx}\n\n{user_input}"
        else:
            stored_input = user_input

        self._session.append(Role.USER, stored_input)

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
                    self._session.history
                )
                if compress_result.triggered:
                    logger.info(
                        _TAG + " auto-compressed: {} rounds, {} batches",
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
            self._session.append(Role.ASSISTANT, final_content)

        # ── 构建最终的 DONE 事件（含完整元数据） ──────────────────
        # Compute aggregate usage across all LLM calls (main loop + sub-agents)
        from rpg_world.rpg_core.agent.agent_types import LLMUsage

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

    async def execute_command(self, command: str) -> CommandResult:
        """将斜杠命令入队执行，返回执行结果。

        通过消息队列串行化，避免与正在处理的 ``send()`` 竞态。
        供 ``/chat/command`` API 端点使用。
        """
        await self._ensure_initialized()
        future: Future[CommandResult] = asyncio.get_event_loop().create_future()
        await self._queue.put(QueueItem(kind=QueueKind.COMMAND, user_input=command, future=future))
        logger.debug(_TAG + " execute_command() enqueued: cmd={!r:.60}", command)
        return await future

    def list_commands(self) -> list["CommandDef"]:
        """返回当前 agent 可用的全部斜杠命令定义。"""
        if self._cmd_dispatcher is None:
            return []
        return self._cmd_dispatcher.list_commands()

    @property
    def history(self) -> list[Message]:
        """Read-only view of the raw conversation history (before RPG transform)."""
        return self._session.history

    @property
    def last_tool_records(self) -> list[ToolCallRecord] | None:
        """Tool-call records from the most recent ``send()`` / ``single_turn()``.

        ``None`` if no tool calls were made.  Useful for displaying
        intermediate tool usage in UIs without persisting them to history.
        """
        return self._last_tool_records

    def clear_history(self) -> None:
        """清空对话历史（RPG 数据保留不动）。

        Also truncates the JSONL file on disk so the next session starts
        fresh.
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

    async def switch_session(self, session_id: str) -> None:
        """原地切换到指定会话，不退出 REPL/Agent。

        依次执行：
        1. 更新 session_id
        2. 重建所有 manager/store（build_rpg_context 接收新 session_id）
        3. 清空并重载历史
        4. 重建工具注册表
        """
        self._session_id = session_id
        self._refresh_rpg_context()
        if self._memory_manager:
            self._memory_manager.init()
        self._session.switch_to(session_id)
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
        return ctx.layer_summary(self._token_counter)

    async def get_context_markdown(self, user_input: str = "") -> str:
        """Build the full 5-layer context and return a Markdown-formatted table.

        Convenience wrapper around ``get_context_info()`` that renders the
        result as a Markdown table string suitable for CLI display or tool
        output.
        """
        await self._ensure_initialized()
        ctx = self._build_ctx_for_inspection(user_input)
        return ctx.to_markdown(self._token_counter)

    def _build_ctx_for_inspection(self, user_input: str = "") -> "RPGContext":
        """Build context for inspection (no _history mutation, no LLM call)."""
        from rpg_world.rpg_core.context.rpg_context import RPGContext

        # Build scene context same way as send()
        scene_ctx = self._scene_tracker.get_context() if self._scene_tracker else None

        test_messages: list[Message] = list(self._session.history)
        if user_input or scene_ctx:
            parts = []
            if scene_ctx:
                parts.append(scene_ctx)
            if user_input:
                parts.append(user_input)
            stored_input = "\n\n".join(parts)
            test_messages.append(Message(role=Role.USER, content=stored_input))
        elif not test_messages:
            test_messages.append(Message(role=Role.USER, content="(no input)"))

        ctx: RPGContext = self._builder.build(
            system_prompt=self._system_prompt,
            messages=test_messages,
            character_mgr=self._character_mgr,
            lorebook_mgr=self._lorebook_mgr,
            status_mgr=self._status_mgr,
            scene_tracker=self._scene_tracker,
        )
        # Wire the hot_history_rounds config for to_markdown()
        ctx._hot_history_rounds = self._builder.config.hot_history_rounds  # type: ignore[attr-defined]
        return ctx

    # ── internals — context & tools ────────────────────────────────────

    def _refresh_rpg_context(self) -> None:
        """构建/刷新 RPG context 管理器（初始化与 reload 共用）。

        重新执行 ``_build_rpg_context()`` 并更新 manager 引用，
        然后刷新 SubAgentContext。不涉及 provider / history / tools 等一次性初始化。
        """
        self._rpg_ctx = _build_rpg_context(
            world_name=self._world_name,
            workspace=self._workspace,
            session_id=self._session_id,
        )
        self._builder = self._rpg_ctx["builder"]
        self._character_mgr = self._rpg_ctx["character_mgr"]
        self._lorebook_mgr = self._rpg_ctx["lorebook_mgr"]
        self._status_mgr = self._rpg_ctx["status_mgr"]
        self._scene_tracker = self._rpg_ctx.get("scene_tracker")
        self._memory_manager = self._rpg_ctx.get("memory_manager")

        # 刷新 SubAgentContext——每个子 Agent 独立实例避免系统提示互相覆盖
        if self._status_sub_agent is not None:
            _sub_ctx_status = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
            self._status_sub_agent.bind_context(_sub_ctx_status)
            # 刷新 StatusSubAgent 的 SceneTracker 工具引用，确保切换 session 后
            # 场景状态写入正确的 session 目录
            if self._scene_tracker is not None:
                self._status_sub_agent._tool_providers.clear()
                self._status_sub_agent.add_tool_provider(self._scene_tracker)
        if self._memory_sub_agent is not None:
            _sub_ctx_memory = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
            self._memory_sub_agent.bind_context(_sub_ctx_memory)

    def _build_transformed_context(self) -> list[Message]:
        """Build the 5-layer RPG context as Message objects."""
        ctx = self._builder.build(
            system_prompt=self._system_prompt,
            messages=self._session.history,
            character_mgr=self._character_mgr,
            lorebook_mgr=self._lorebook_mgr,
            status_mgr=self._status_mgr,
            scene_tracker=self._scene_tracker,
        )
        return ctx.to_message_objects()

    def _setup_tool_registry(self) -> None:
        """Create and populate the ToolRegistry with built-in file tools."""
        from rpg_world.rpg_core.utils.path_utils import resolve_workspace_root, PACKAGE_ROOT

        ws_root = resolve_workspace_root(PACKAGE_ROOT, self._workspace)
        self._tool_registry = ToolRegistry()
        self._tool_registry.register_all([
            ListFilesTool(ws_root),
            ReadFileTool(ws_root),
            WriteFileTool(ws_root),
            GrepTool(ws_root),
        ])
        if self._scene_tracker:
            self._tool_registry.register_all(self._scene_tracker.get_tools())
        if self._extra_tools:
            self._tool_registry.register_all(self._extra_tools)

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        self._system_prompt = PromptManager(self._world_name).system_prompt
        self._session.load()

        # ── MemoryManager 初始化（仅注册 FileWatcher） ─────────
        if self._memory_manager:
            self._memory_manager.init()

        self._provider = OpenAIProvider(
            model=self._model,
            api_key=self._api_key,
            base_url=self._base_url,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        # ── StatusSubAgent ────────────────────────────────────────────
        status_cfg = settings.status_sub_agent_config
        status_provider, status_provider_config = _resolve_sub_agent_provider(
            name="status_sub_agent",
            cfg=status_cfg,
            shared_provider=self._provider,
            main_api_key=self._api_key,
            main_base_url=self._base_url,
            main_max_tokens=self._max_tokens,
            main_temperature=self._temperature,
        )
        self._status_sub_agent = StatusSubAgent(
            provider=status_provider,
            provider_config=status_provider_config,
            enabled=status_cfg.get("enabled", True),
        )
        if self._scene_tracker:
            self._status_sub_agent.add_tool_provider(self._scene_tracker)
        _status_ctx = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
        self._status_sub_agent.bind_context(_status_ctx)

        # ── MemorySubAgent ────────────────────────────────────────────
        memory_cfg = settings.memory_sub_agent_config
        memory_provider, memory_provider_config = _resolve_sub_agent_provider(
            name="memory_sub_agent",
            cfg=memory_cfg,
            shared_provider=self._provider,
            main_api_key=self._api_key,
            main_base_url=self._base_url,
            main_max_tokens=self._max_tokens,
            main_temperature=self._temperature,
        )
        self._memory_sub_agent = MemorySubAgent(
            provider=memory_provider,
            provider_config=memory_provider_config,
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

        # 子 Agent 命令
        if self._status_sub_agent is not None and self._status_sub_agent.enabled:
            self._cmd_dispatcher.register_sub_agent(self._status_sub_agent)
        if self._memory_sub_agent is not None and self._memory_sub_agent.enabled:
            self._cmd_dispatcher.register_sub_agent(self._memory_sub_agent)

        self._setup_tool_registry()

        # 启动文件监听（管理器已在 BaseManager.__init__ 中注册路径）
        get_watcher().start()

        # 启动消息队列消费者
        self._consumer_task = asyncio.create_task(self._queue_consumer())

        self._initialized = True


def _build_rpg_context(world_name: str, workspace: str, session_id: str) -> dict[str, object]:
    """Inline import of the factory to keep the top level free of side effects."""
    from rpg_world.rpg_core.context.factory import build_rpg_context

    return build_rpg_context(world_name=world_name, workspace=workspace, session_id=session_id)


_SUB_AGENT_PROVIDER_MODES = frozenset(LLM_PROVIDER_MODES)


def _resolve_sub_agent_provider(
    *,
    name: str,
    cfg: dict[str, Any],
    shared_provider: LLMProvider | None,
    main_api_key: str | None,
    main_base_url: str | None,
    main_max_tokens: int | None,
    main_temperature: float | None,
) -> tuple[LLMProvider | None, SubAgentProviderConfig]:
    if not isinstance(cfg, dict):
        cfg = {}

    enabled = settings._as_bool(cfg.get("enabled", True), True)
    if not enabled:
        return None, SubAgentProviderConfig(mode=LLM_PROVIDER_SHARED)

    mode = str(cfg.get("llm_provider") or LLM_PROVIDER_SHARED).strip()
    if mode not in _SUB_AGENT_PROVIDER_MODES:
        raise ValueError(
            f"{name} config invalid: llm_provider must be one of {', '.join(LLM_PROVIDER_MODES)}; got {mode!r}"
        )

    if mode == LLM_PROVIDER_SHARED:
        if shared_provider is None:
            raise ValueError(f"{name} config invalid: llm_provider={LLM_PROVIDER_SHARED} requires main Agent provider")
        return shared_provider, SubAgentProviderConfig(mode=LLM_PROVIDER_SHARED)

    if mode == LLM_PROVIDER_OPENAI:
        openai_cfg = _as_mapping(cfg.get("openai"), f"{name}.openai")
        model = _non_empty(openai_cfg.get("model"))
        if not model:
            raise ValueError(f"{name} config invalid: openai.model is required when llm_provider={LLM_PROVIDER_OPENAI}")
        api_key = _non_empty(openai_cfg.get("api_key"))
        if not api_key:
            api_key_env = _non_empty(openai_cfg.get("api_key_env"))
            if api_key_env:
                api_key = _non_empty(os.environ.get(api_key_env))
        return None, SubAgentProviderConfig(
            mode=LLM_PROVIDER_OPENAI,
            openai={
                "model": model,
                "api_key": api_key or main_api_key,
                "base_url": openai_cfg.get("base_url") or main_base_url,
                "max_tokens": openai_cfg.get("max_tokens")
                if openai_cfg.get("max_tokens") is not None else main_max_tokens,
                "temperature": openai_cfg.get("temperature")
                if openai_cfg.get("temperature") is not None else main_temperature,
            },
        )

    if not settings.memory_settings.llama_process_enabled:
        raise ValueError(
            f"{name} config invalid: llm_provider={LLM_PROVIDER_LLAMA} requires memory.llama_process_enabled=true"
        )
    llama_cfg = _as_mapping(cfg.get("llama"), f"{name}.llama")
    raw_model_path = _non_empty(llama_cfg.get("model_path"))
    if not raw_model_path:
        raise ValueError(f"{name} config invalid: llama.model_path is required when llm_provider={LLM_PROVIDER_LLAMA}")
    model_path = _resolve_llama_model_path(raw_model_path)
    if not model_path.is_file():
        raise ValueError(f"{name} config invalid: GGUF model not found: {model_path}")
    return None, SubAgentProviderConfig(
        mode=LLM_PROVIDER_LLAMA,
        llama={
            "model_path": str(model_path),
            "n_ctx": llama_cfg.get("n_ctx", 2048),
            "n_gpu_layers": llama_cfg.get("n_gpu_layers", 0),
            "request_timeout_ms": llama_cfg.get("request_timeout_ms", 60000),
            "max_tokens": llama_cfg.get("max_tokens", 512),
            "temperature": llama_cfg.get("temperature", 0.0),
        },
    )


def _as_mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} config invalid: must be a mapping")
    return value


def _non_empty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_llama_model_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (PACKAGE_ROOT / path).resolve()


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
