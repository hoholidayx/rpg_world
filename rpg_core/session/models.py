"""Typed state and projections for the session domain."""

from __future__ import annotations

from dataclasses import dataclass, field

from rpg_core.context.rpg_context import Message


@dataclass(frozen=True)
class ContextHistorySnapshot:
    """Main-Agent history projection derived from ``summary_processed``."""

    messages: tuple[Message, ...]
    filtered_message_count: int


@dataclass
class SessionRuntimeState:
    """Mutable in-process state shared by the session domain services."""

    messages: list[Message] = field(default_factory=list)
    active_turn_id: int | None = None
    turn_seq_by_turn: dict[int, int] = field(default_factory=dict)
    story_memory_processed_message_keys: set[int] = field(default_factory=set)
    summary_processed_message_keys: set[int] = field(default_factory=set)
