"""Copy-on-write message scratch for one agent turn."""

from __future__ import annotations

from dataclasses import dataclass, field

from rpg_core.context.rpg_context import Message, Role


@dataclass
class MessageScratch:
    """Memory-only staged messages for one turn."""

    turn_id: int
    base_history: list[Message]
    staged_messages: list[Message] = field(default_factory=list)

    def stage(self, role: Role | str, content: str) -> Message:
        message = Message(
            role=role,
            content=str(content or ""),
            turn_id=self.turn_id,
            seq_in_turn=len(self.staged_messages) + 1,
        )
        self.staged_messages.append(message)
        return message

    def history_for_context(self) -> list[Message]:
        return [*self.base_history, *self.staged_messages]
