"""Immutable, provider-ready context shared by adjudication stages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rpg_core.context.models import Message, Role


@dataclass(frozen=True, slots=True)
class AdjudicationContextMessage:
    """One immutable message in the module-neutral adjudication prefix."""

    role: Role
    content: str

    def to_message(self) -> Message:
        return Message(role=self.role, content=self.content)


@dataclass(frozen=True, slots=True)
class AdjudicationContextSnapshot:
    """Rendered authority, canon, character, and Memory context for one turn."""

    messages: tuple[AdjudicationContextMessage, ...] = ()

    @classmethod
    def from_messages(
        cls,
        messages: Iterable[Message],
    ) -> "AdjudicationContextSnapshot":
        return cls(
            messages=tuple(
                AdjudicationContextMessage(
                    role=message.role,
                    content=message.content,
                )
                for message in messages
                if message.content.strip()
            )
        )

    def to_messages(self) -> list[Message]:
        """Return fresh mutable wire-message wrappers for one stage."""

        return [message.to_message() for message in self.messages]

    @property
    def active(self) -> bool:
        return bool(self.messages)
