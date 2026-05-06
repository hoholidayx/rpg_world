"""RPG World agent hook — a concrete AgentHook subclass.

Hooks implemented:
  1. `before_iteration`` — receives the actual ``messages_for_model``
     (the filtered/processed messages that will be sent to the LLM),
     allowing per-turn inspection or modification.
"""

from __future__ import annotations

from typing import Any

from nanobot.agent import AgentHook, AgentHookContext


class RpgWorldHook(AgentHook):
    """Appends an RPG framing to the system prompt and logs model-bound messages."""

    def __init__(self, world_name: str = "Nanobot Realm") -> None:
        super().__init__()
        self.world_name = world_name
        self.system_prompt: str | None = None

    async def before_iteration(self, context: AgentHookContext) -> None:
        """Remove system messages from context and inject RPG World context."""
        context.messages = [msg for msg in context.messages if msg.get("role") != "system"]
        for msg in reversed(context.messages):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content")
            if isinstance(content, str) and "[Runtime Context" in content:
                new_content = self._update_runtime_context(content)
                if new_content is not None:
                    msg["content"] = new_content
                break

    def _update_runtime_context(self, content: str) -> str | None:
        """Override to customize the runtime context block in a message.

        The default implementation appends the RPG world tag after the runtime
        context block. Return ``None`` to leave the message unchanged.

        Args:
            content: The full message text containing the runtime context block.

        Returns:
            Modified message content, or ``None`` if no modification is needed.
        """
        rpg_tag = "[RPG World: {}]".format(self.world_name)
        if rpg_tag in content:
            return None
        end_marker = "[/Runtime Context]"
        end_pos = content.find(end_marker)
        if end_pos < 0:
            return None
        split = end_pos + len(end_marker)
        return content[:split] + "\n" + rpg_tag + content[split:]
