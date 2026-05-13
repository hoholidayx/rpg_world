"""RPGGameAgent — orchestrates history, 6-layer context build, and LLM call."""

from __future__ import annotations

from typing import Any

from rpg_world.agent.openai_provider import OpenAIProvider
from rpg_world.agent.prompt import PromptManager


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
    ) -> None:
        self._session_id = session_id
        self._world_name = world_name
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._temperature = temperature

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

    # ── public API ─────────────────────────────────────────────────────

    async def send(self, user_input: str) -> str:
        """Send user text and return the assistant reply.

        Steps:
          1. Lazy-init on first call.
          2. Append ``{"role": "user", "content": user_input}`` to history.
          3. Build the 6-layer RPG context via ``RPGContextBuilder.build()``.
          4. Call OpenAPI with the transformed messages.
          5. Append the reply to history.
          6. Return the reply text.
        """
        await self._ensure_initialized()

        self._history.append({"role": "user", "content": user_input})

        transformed = self._builder.build(
            system_prompt=self._system_prompt,
            messages=self._history,
            character_mgr=self._character_mgr,
            lorebook_mgr=self._lorebook_mgr,
            milestone_mgr=self._milestone_mgr,
            status_mgr=self._status_mgr,
        )

        reply = await self._provider.chat(transformed)

        self._history.append({"role": "assistant", "content": reply})
        return reply

    @property
    def history(self) -> list[dict]:
        """Read-only view of the raw conversation history (before RPG transform)."""
        return list(self._history)

    def clear_history(self) -> None:
        """Reset history to just the system prompt (RPG data stays loaded)."""
        if self._initialized:
            self._history = [{"role": "system", "content": self._system_prompt}]

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

    # ── internals ──────────────────────────────────────────────────────

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

        self._provider = OpenAIProvider(
            model=self._model,
            api_key=self._api_key,
            base_url=self._base_url,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        self._initialized = True


def _build_rpg_context(world_name: str, session_id: str) -> dict[str, Any]:
    """Inline import of the factory to keep the top level free of side effects."""
    from rpg_world.rpg_core.context.factory import build_rpg_context

    return build_rpg_context(world_name=world_name, session_id=session_id)
