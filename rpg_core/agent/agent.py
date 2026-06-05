"""RPGGameAgent — orchestrates history, 5-layer context build, and LLM call."""

from __future__ import annotations

import json
import time as _time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from loguru import logger

from rpg_world.rpg_core.agent.base_provider import LLMProvider
from rpg_world.rpg_core.agent.loop import AgentReply, ToolCallRecord, run_chat_loop, run_chat_loop_stream
from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider
from rpg_world.rpg_core.agent.prompt import PromptManager
from rpg_world.rpg_core.agent.sub_agents import StatusSubAgent, SubAgentContext
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
        self._history: list[dict] = []
        self._tool_registry: ToolRegistry | None = None
        self._last_tool_records: list[ToolCallRecord] | None = None
        self._status_sub_agent: StatusSubAgent | None = None

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
        before = len(self._history)
        original = self._history_enabled
        self._history_enabled = record_history
        try:
            reply = await self.send(user_input)
        finally:
            self._history_enabled = original
        # Roll back history — single_turn must be stateless
        del self._history[before:]
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

        # ── TurnStats 聚合器（追踪本轮所有 LLM 调用） ──────────────
        turn_stats = TurnStats(started_at=_time.monotonic())

        # ── 状态表预更新（~1-2K tokens，避免主 loop round-trip） ──────
        status_records = None
        if self._status_sub_agent and self._scene_tracker:
            scene_ctx_before = self._scene_tracker.get_context()
            sub_result = await self._status_sub_agent.update(
                history=self._history,
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

        self._history.append({"role": "user", "content": stored_input})
        self._append_history("user", stored_input)

        messages = self._build_transformed_context()
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

        self._history.append({"role": "assistant", "content": reply_text})
        self._append_history("assistant", reply_text)
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

        # ── TurnStats 聚合器 ───────────────────────────────────────
        turn_stats = TurnStats(started_at=_time.monotonic())

        # ── 状态表预更新（~1-2K tokens，避免主 loop round-trip） ────
        status_records = None
        if self._status_sub_agent and self._scene_tracker:
            scene_ctx_before = self._scene_tracker.get_context()
            sub_result = await self._status_sub_agent.update(
                history=self._history,
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

        self._history.append({"role": "user", "content": stored_input})
        self._append_history("user", stored_input)

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
            self._history.append({"role": "assistant", "content": final_content})
            self._append_history("assistant", final_content)

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
        return list(self._history)

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
            self._history = []
        if self._history_enabled:
            path = self._history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

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
        self._history = []
        if self._history_enabled:
            self._load_history_from_disk()
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

        test_messages = list(self._history)
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

    # ── internals — context & tools ────────────────────────────────────

    def _refresh_rpg_context(self) -> None:
        """构建/刷新 RPG context 管理器（初始化与 reload 共用）。

        重新执行 ``_build_rpg_context()`` 并更新 manager 引用，
        然后刷新 SubAgentContext。不涉及 provider / history / tools 等一次性初始化。
        """
        ctx = _build_rpg_context(
            world_name=self._world_name,
            session_id=self._session_id,
        )
        self._builder = ctx["builder"]
        self._character_mgr = ctx["character_mgr"]
        self._lorebook_mgr = ctx["lorebook_mgr"]
        self._status_mgr = ctx["status_mgr"]
        self._scene_tracker = ctx.get("scene_tracker")

        # 刷新 SubAgentContext（世界书 + 角色卡）
        _sub_ctx = SubAgentContext.from_managers(
            system_prompt=self._system_prompt,
            character_mgr=self._character_mgr,
            lorebook_mgr=self._lorebook_mgr,
        )
        if self._status_sub_agent is not None:
            self._status_sub_agent.bind_context(_sub_ctx)

    def _build_transformed_context(self) -> list[dict]:
        """Build the 5-layer RPG context and flatten to message list."""
        ctx = self._builder.build(
            system_prompt=self._system_prompt,
            messages=self._history,
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


    # ── internals — history persistence ────────────────────────────────

    def _history_path(self) -> Path:
        """Return the JSONL file path for this session's persisted history."""
        return settings.get_history_path(self._session_id)

    def _load_history_from_disk(self) -> None:
        """Append persisted messages from the JSONL file to ``_history``."""
        path = self._history_path()
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._history.append(msg)
                except json.JSONDecodeError:
                    continue

    def _append_history(self, role: str, content: str) -> None:
        """Append one message to the JSONL file (no-op if history disabled)."""
        if not self._history_enabled:
            return
        path = self._history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"role": role, "content": content}, ensure_ascii=False) + "\n")

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        # 构建 RPG context 管理器（与 reload 共用同一套逻辑）
        self._refresh_rpg_context()

        self._system_prompt = PromptManager(self._world_name).system_prompt
        self._history = []

        if self._history_enabled:
            self._load_history_from_disk()

        self._provider = OpenAIProvider(
            model=self._model,
            api_key=self._api_key,
            base_url=self._base_url,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        # ── SubAgentContext（世界书 + 角色卡，供所有子 Agent 共享） ──
        _sub_ctx = SubAgentContext.from_managers(
            system_prompt=self._system_prompt,
            character_mgr=self._character_mgr,
            lorebook_mgr=self._lorebook_mgr,
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
        self._status_sub_agent.bind_context(_sub_ctx)

        self._setup_tool_registry()

        # 启动文件监听（管理器已在 BaseManager.__init__ 中注册路径）
        get_watcher().start()

        self._initialized = True


def _build_rpg_context(world_name: str, session_id: str) -> dict[str, Any]:
    """Inline import of the factory to keep the top level free of side effects."""
    from rpg_world.rpg_core.context.factory import build_rpg_context

    return build_rpg_context(world_name=world_name, session_id=session_id)
