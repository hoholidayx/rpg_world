"""Copy-on-write message scratch for one agent turn."""

from __future__ import annotations

from dataclasses import dataclass, field

from rpg_core.agent.turn.models import DEFAULT_TURN_MODE
from rpg_core.context.models import Message, Role


@dataclass
class MessageScratch:
    """Memory-only staged messages for one turn."""

    turn_id: int
    base_history: list[Message]
    mode: str = DEFAULT_TURN_MODE.value
    staged_messages: list[Message] = field(default_factory=list)

    def stage(self, role: Role | str, content: str) -> Message:
        message = Message(
            role=role,
            content=str(content or ""),
            mode=self.mode,
            turn_id=self.turn_id,
            seq_in_turn=len(self.staged_messages) + 1,
        )
        self.staged_messages.append(message)
        return message
