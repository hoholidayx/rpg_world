"""RPGGameAgent — orchestrates history, 5-layer context build, and LLM call."""

from __future__ import annotations

import time as _time
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from rpg_world.rpg_core.agent.base_provider import LLMProvider
from rpg_world.rpg_core.agent.loop import AgentReply, ToolCallRecord, run_chat_loop, run_chat_loop_stream
from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider
from rpg_world.rpg_core.agent.command import CommandDispatcher
from rpg_world.rpg_core.agent.prompt import PromptManager
from rpg_world.rpg_core.agent.sub_agents import (
    MemorySubAgent,
    StatusSubAgent,
    SubAgentContext,
)
from rpg_world.rpg_core.agent.tokenizer import TiktokenTokenCounter, TokenCounter
from rpg_world.rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnStats
from rpg_world.rpg_core.agent.tools import (
    BaseTool,
    GrepTool,
    ListFilesTool,
    ReadFileTool,
    ToolRegistry,
    WriteFileTool,
)
from rpg_world.rpg_core.scene import SceneTracker
from rpg_world.rpg_core.session import SessionManager
from rpg_world.rpg_core.settings import settings
from rpg_world.rpg_core.utils.watcher import get_watcher

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
        self._world_name = world_name
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._history_enabled = history_enabled
        self._extra_tools = tools or []
        self._token_counter = token_counter or TiktokenTokenCounter()

        # Lazy-init
        self._initialized: bool = False
        self._builder: Any = None
        self._character_mgr: Any = None
        self._lorebook_mgr: Any = None
        self._status_mgr: Any = None
        self._scene_tracker: SceneTracker | None = None
        self._provider: LLMProvider | None = None
        self._system_prompt: str = ""
        self._session = SessionManager(
            session_id=self._session_id,
            history_enabled=self._history_enabled,
        )
        self._tool_registry: ToolRegistry | None = None
        self._last_tool_records: list[ToolCallRecord] | None = None
        self._status_sub_agent: StatusSubAgent | None = None
        self._memory_sub_agent: MemorySubAgent | None = None
        self._rpg_ctx: dict[str, Any] = {}
        self._cmd_dispatcher: CommandDispatcher | None = None

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
        """Send user text and return a structured ``AgentReply``.

        May involve multiple LLM round-trips when tool calls are needed
        (the chat loop).  The 5-layer context is built once; subsequent
        iterations append raw assistant/tool messages.

        The user message in ``_history`` / JSONL includes the ``[scene]``
        context so that MemorySubAgent can see scene timeline during
        summarization (it filters ``role == "system"`` messages).
        """
        

        await self._ensure_initialized()

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

        self._session.append("user", stored_input)

        messages = self._build_transformed_context()
        if settings.verbose_logging:
            sys_msgs = sum(1 for m in messages if m.get("role") == "system")
            user_msgs = sum(1 for m in messages if m.get("role") == "user")
            asst_msgs = sum(1 for m in messages if m.get("role") == "assistant")
            total_chars = sum(len(m.get("content", "")) for m in messages)
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
        if settings.verbose_logging and turn_stats.calls:
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

        self._session.append("assistant", reply_text)
        return result

    async def send_stream(self, user_input: str) -> AsyncIterator[AgentStreamEvent]:
        """Streaming variant of ``send()``.

        Yields ``AgentStreamEvent`` objects for real-time consumption.
        The stream ends with a ``DONE`` event carrying aggregated
        usage/stats metadata.

        Usage::

            async for event in agent.send_stream("look around"):
                match event.kind:
                    case StreamEventKind.TEXT:
                        print(event.content, end="", flush=True)
                    case StreamEventKind.DONE:
                        _print_stats(event)

        StatusSubAgent pre-update, scene context embedding, history
        persistence all mirror ``send()`` exactly.
        """
        await self._ensure_initialized()

        # ── 斜杠命令分发（不走 LLM） ─────────────────────────────────
        if self._cmd_dispatcher and self._cmd_dispatcher.is_command(user_input):
            cmd_result = await self._cmd_dispatcher.dispatch(user_input)
            if cmd_result.handled:
                yield AgentStreamEvent(
                    kind=StreamEventKind.DONE,
                    content=cmd_result.reply,
                    model=self._model,
                )
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

        # ── Build scene context and embed into stored user message ──
        scene_ctx = self._scene_tracker.get_context() if self._scene_tracker else None
        if scene_ctx:
            stored_input = f"{scene_ctx}\n\n{user_input}"
        else:
            stored_input = user_input

        self._session.append("user", stored_input)

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
                    yield event
        except Exception as exc:
            logger.error("{} send_stream error: {}", _TAG, exc)
            yield AgentStreamEvent(
                kind=StreamEventKind.ERROR,
                content=str(exc),
            )
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
            self._session.append("assistant", final_content)

        # ── 构建最终的 DONE 事件（含完整元数据） ──────────────────
        # Compute aggregate usage across all LLM calls (main loop + sub-agents)
        from rpg_world.rpg_core.agent.agent_types import LLMUsage

        total_pt = turn_stats.total_prompt_tokens
        total_ct = turn_stats.total_completion_tokens
        total_cached = turn_stats.total_cached_tokens
        aggregate_usage = LLMUsage(
            prompt_tokens=total_pt,
            completion_tokens=total_ct,
            total_tokens=total_pt + total_ct,
            prompt_tokens_details={"cached_tokens": total_cached} if total_cached else None,
        )

        if final_event is not None:
            final_event.duration_ms = turn_stats.total_duration_ms
            final_event.usage = aggregate_usage
            final_event.stats = turn_stats
            yield final_event
        else:
            yield AgentStreamEvent(
                kind=StreamEventKind.DONE,
                content=final_content,
                usage=aggregate_usage,
                duration_ms=turn_stats.total_duration_ms,
                model=self._model,
            )

    @property
    def history(self) -> list[dict]:
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
        from rpg_world.rpg_core.context.rpg_context import LayerInfo

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

        test_messages = list(self._session.history)
        if user_input or scene_ctx:
            parts = []
            if scene_ctx:
                parts.append(scene_ctx)
            if user_input:
                parts.append(user_input)
            stored_input = "\n\n".join(parts)
            test_messages.append({"role": "user", "content": stored_input})
        elif not test_messages:
            test_messages.append({"role": "user", "content": "(no input)"})

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

    # ── compact history (manual summary trigger) ──────────────────────

    async def compact_history(
        self,
        compress_rounds: int | None = None,
        keep_rounds: int | None = None,
    ) -> dict[str, Any]:
        """压缩最老的对话轮次为摘要。

        从最早的 user 轮次开始，压缩 ``compress_rounds`` 轮，保留最近
        ``keep_rounds`` 轮不动。压缩完成后从 ``_history`` 中移除已压缩
        的消息，并重写 JSONL 文件。

        Args:
            compress_rounds:
                从最早的用户轮次开始压缩 N 轮。默认从 settings 读取。
            keep_rounds:
                保留最近 N 轮不压缩。默认从 settings 读取。

        Returns:
            包含 ``summary_text``、``compress_rounds``、``kept_rounds``、
            ``previous_history_msgs``、``history_after_msgs`` 的 dict。
        """
        await self._ensure_initialized()

        compress_rounds = compress_rounds or settings.memory_compress_rounds
        keep_rounds = keep_rounds or settings.memory_keep_rounds

        user_indices = [i for i, m in enumerate(self._session.history) if m.get("role") == "user"]
        total = len(user_indices)
        available = total - keep_rounds
        if available <= 0:
            logger.info(
                _TAG + " compact skipped: history too short ({} user rounds <= {} keep)",
                total, keep_rounds,
            )
            return {"skipped": True, "reason": f"history too short ({total} <= {keep_rounds})"}

        actual = min(compress_rounds, available)
        compress_end = user_indices[actual] if actual < len(user_indices) else len(self._session.history)

        logger.info(
            _TAG + " compact: total={} user rounds, compress={}, keep={}",
            total, actual, keep_rounds,
        )

        compress_window = self._session.history[:compress_end]
        result = await self._memory_sub_agent.process({"summary": compress_window})
        summary_text = ""
        if result.summary_generated:
            summaries = self._builder._summary_store.get_all_summaries()
            summary_text = summaries[-1] if summaries else ""
            logger.info(
                _TAG + " summary generated: {} chars", len(summary_text),
            )

        # 截断（委派 SessionManager）
        before_len = len(self._session.history)
        self._session.truncate(compress_end)
        after_len = len(self._session.history)
        self._session.increment_compacted_rounds(actual)

        logger.info(
            _TAG + " compact: deleted {} msgs, history now {} msgs",
            before_len - after_len, after_len,
        )

        return {
            "summary_text": summary_text,
            "compress_rounds": actual,
            "kept_rounds": keep_rounds,
            "previous_history_msgs": before_len,
            "history_after_msgs": after_len,
        }

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

        # 刷新 SubAgentContext——每个子 Agent 独立实例避免系统提示互相覆盖
        if self._status_sub_agent is not None:
            _sub_ctx_status = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
            self._status_sub_agent.bind_context(_sub_ctx_status)
        if self._memory_sub_agent is not None:
            _sub_ctx_memory = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
            self._memory_sub_agent.bind_context(_sub_ctx_memory)

    def _build_transformed_context(self) -> list[dict]:
        """Build the 5-layer RPG context and flatten to message list."""
        ctx = self._builder.build(
            system_prompt=self._system_prompt,
            messages=self._session.history,
            character_mgr=self._character_mgr,
            lorebook_mgr=self._lorebook_mgr,
            status_mgr=self._status_mgr,
            scene_tracker=self._scene_tracker,
        )
        return ctx.to_messages()

    def _setup_tool_registry(self) -> None:
        """Create and populate the ToolRegistry with built-in file tools."""
        ws_root = settings.workspace_root
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

        # 构建 RPG context 管理器（与 reload 共用同一套逻辑）
        self._refresh_rpg_context()

        self._system_prompt = PromptManager(self._world_name).system_prompt
        self._session.load()

        self._provider = OpenAIProvider(
            model=self._model,
            api_key=self._api_key,
            base_url=self._base_url,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        # ── StatusSubAgent ────────────────────────────────────────────
        status_cfg = settings.status_sub_agent_config
        status_model = status_cfg.get("model")
        self._status_sub_agent = StatusSubAgent(
            provider=None if status_model else self._provider,
            model=status_model or self._model,
            api_key=status_cfg.get("api_key") or self._api_key,
            base_url=status_cfg.get("base_url") or self._base_url,
            enabled=status_cfg.get("enabled", True),
        )
        if self._scene_tracker:
            self._status_sub_agent.add_tool_provider(self._scene_tracker)
        _status_ctx = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
        self._status_sub_agent.bind_context(_status_ctx)

        # ── MemorySubAgent ────────────────────────────────────────────
        memory_cfg = settings.memory_sub_agent_config
        memory_model = memory_cfg.get("model")
        self._memory_sub_agent = MemorySubAgent(
            provider=None if memory_model else self._provider,
            model=memory_model or self._model,
            api_key=memory_cfg.get("api_key") or self._api_key,
            base_url=memory_cfg.get("base_url") or self._base_url,
            enabled=memory_cfg.get("enabled", True),
            summary_store=self._builder._summary_store if self._builder else None,
            max_window_rounds=settings.memory_keep_rounds,
        )
        _memory_ctx = _build_sub_agent_context(self._character_mgr, self._lorebook_mgr)
        self._memory_sub_agent.bind_context(_memory_ctx)

        # ── CommandDispatcher ─────────────────────────────────────────
        self._cmd_dispatcher = CommandDispatcher(agent=self)
        # 内置命令
        async def _cmd_clear(agent, args):
            agent.clear_history()
            return "对话历史已清空。"

        async def _cmd_reload(agent, args):
            await agent.reload_rpg_context()
            return "RPG 数据已重新加载。"

        async def _cmd_context(agent, args):
            return await agent.get_context_markdown()

        self._cmd_dispatcher.register_builtin(
            "/clear", "清空当前会话的对话历史",
            "重置对话上下文，清除所有已发送的消息记录。", _cmd_clear,
        )
        self._cmd_dispatcher.register_builtin(
            "/reload", "重新加载 RPG 数据（角色卡、世界书）",
            "从磁盘重新读取角色卡和世界书文件变更。", _cmd_reload,
        )
        self._cmd_dispatcher.register_builtin(
            "/context", "查看当前上下文结构和 token 用量",
            "显示 5 层 RPG 上下文的每层信息。", _cmd_context,
        )
        # 子 Agent 命令
        if self._status_sub_agent is not None:
            self._cmd_dispatcher.register_sub_agent(self._status_sub_agent)
        if self._memory_sub_agent is not None:
            self._cmd_dispatcher.register_sub_agent(self._memory_sub_agent)

        self._setup_tool_registry()

        # 启动文件监听（管理器已在 BaseManager.__init__ 中注册路径）
        get_watcher().start()

        self._initialized = True


def _build_rpg_context(world_name: str, session_id: str) -> dict[str, Any]:
    """Inline import of the factory to keep the top level free of side effects."""
    from rpg_world.rpg_core.context.factory import build_rpg_context

    return build_rpg_context(world_name=world_name, session_id=session_id)


def _build_sub_agent_context(
    character_mgr: Any,
    lorebook_mgr: Any,
) -> SubAgentContext:
    """从 Manager 读取已启用条目，构造 SubAgentContext。

    主 Agent 读 Manager 后直接传 data，SubAgentContext 不依赖 Manager 类型。
    """
    lorebook_entries: list[dict[str, Any]] = []
    if lorebook_mgr is not None:
        try:
            lorebook_entries = lorebook_mgr.list_enabled_entries()
        except Exception:
            pass

    characters: list[dict[str, Any]] = []
    if character_mgr is not None:
        try:
            characters = character_mgr.list_enabled_characters()
        except Exception:
            pass

    return SubAgentContext(
        lorebook_entries=lorebook_entries,
        characters=characters,
    )
