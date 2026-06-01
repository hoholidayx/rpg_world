"""RPGGameAgent — orchestrates history, 5-layer context build, and LLM call."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rpg_world.rpg_core.agent.loop import AgentReply, ToolCallRecord, run_chat_loop
from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider
from rpg_world.rpg_core.agent.prompt import PromptManager
from rpg_world.rpg_core.agent.tools import (
    BaseTool,
    GrepTool,
    ListFilesTool,
    ReadFileTool,
    ToolRegistry,
    WriteFileTool,
)
from rpg_world.rpg_core.settings import settings


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

        # Lazy-init
        self._initialized: bool = False
        self._builder: Any = None
        self._character_mgr: Any = None
        self._lorebook_mgr: Any = None
        self._milestone_mgr: Any = None
        self._status_mgr: Any = None
        self._provider: OpenAIProvider | None = None
        self._system_prompt: str = ""
        self._history: list[dict] = []
        self._tool_registry: ToolRegistry | None = None
        self._last_tool_records: list[ToolCallRecord] | None = None

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
        """
        await self._ensure_initialized()

        self._history.append({"role": "user", "content": user_input})
        self._append_history("user", user_input)

        messages = self._build_transformed_context()
        schemas = self._tool_registry.get_openai_schemas() if self._tool_registry else None

        reply_text, records = await run_chat_loop(
            provider=self._provider,
            tool_registry=self._tool_registry,
            messages=messages,
            schemas=schemas,
        )
        self._last_tool_records = records

        if settings.include_tool_records:
            result = AgentReply(text=reply_text, tool_records=records or None)
        else:
            result = AgentReply(text=reply_text)

        self._history.append({"role": "assistant", "content": reply_text})
        self._append_history("assistant", reply_text)
        return result

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
        """Reset history to just the system prompt (RPG data stays loaded).

        Also truncates the JSONL file on disk so the next session starts
        fresh.
        """
        if self._initialized:
            self._history = [{"role": "system", "content": self._system_prompt}]
        if self._history_enabled:
            path = self._history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

    async def reload_rpg_context(self) -> None:
        """Re-run ``build_rpg_context()`` to pick up filesystem changes."""
        if not self._initialized:
            return
        ctx = _build_rpg_context(
            world_name=self._world_name,
            session_id=self._session_id,
        )
        self._builder = ctx["builder"]
        self._character_mgr = ctx["character_mgr"]
        self._lorebook_mgr = ctx["lorebook_mgr"]
        self._milestone_mgr = ctx["milestone_mgr"]
        self._status_mgr = ctx["status_mgr"]

    # ── internals — context & tools ────────────────────────────────────

    def _build_transformed_context(self) -> list[dict]:
        """Build the 5-layer RPG context from the current history."""
        return self._builder.build(
            system_prompt=self._system_prompt,
            messages=self._history,
            character_mgr=self._character_mgr,
            lorebook_mgr=self._lorebook_mgr,
            milestone_mgr=self._milestone_mgr,
            status_mgr=self._status_mgr,
        )

    def _setup_tool_registry(self) -> None:
        """Create and populate the ToolRegistry with built-in file tools."""
        ws_root = Path(settings.history_path).parent
        self._tool_registry = ToolRegistry()
        self._tool_registry.register_all([
            ListFilesTool(ws_root),
            ReadFileTool(ws_root),
            WriteFileTool(ws_root),
            GrepTool(ws_root),
        ])
        if self._extra_tools:
            self._tool_registry.register_all(self._extra_tools)


    # ── internals — history persistence ────────────────────────────────

    def _history_path(self) -> Path:
        """Return the JSONL file path for this session's persisted history."""
        return Path(settings.history_path) / f"{self._session_id}.jsonl"

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

        ctx = _build_rpg_context(
            world_name=self._world_name,
            session_id=self._session_id,
        )
        self._builder = ctx["builder"]
        self._character_mgr = ctx["character_mgr"]
        self._lorebook_mgr = ctx["lorebook_mgr"]
        self._milestone_mgr = ctx["milestone_mgr"]
        self._status_mgr = ctx["status_mgr"]

        self._system_prompt = PromptManager(self._world_name).system_prompt
        self._history = [{"role": "system", "content": self._system_prompt}]

        if self._history_enabled:
            self._load_history_from_disk()

        self._provider = OpenAIProvider(
            model=self._model,
            api_key=self._api_key,
            base_url=self._base_url,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        self._setup_tool_registry()

        self._initialized = True


def _build_rpg_context(world_name: str, session_id: str) -> dict[str, Any]:
    """Inline import of the factory to keep the top level free of side effects."""
    from rpg_world.rpg_core.context.factory import build_rpg_context

    return build_rpg_context(world_name=world_name, session_id=session_id)
