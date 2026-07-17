"""Shared turn grouping and memory-processing candidate selection.

The algorithms in this module operate only on the public ``SessionManager``
surface.  Keeping them in the session domain prevents summary code from
depending on a concrete Agent or SubAgent implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rpg_core.agent.turn.models import TurnMode
from rpg_core.context.rpg_context import Message

if TYPE_CHECKING:
    from rpg_core.session.manager import SessionManager


_ALLOWED_MEMORY_MODES = frozenset({TurnMode.IC.value, TurnMode.GM.value})


@dataclass(frozen=True)
class MemoryTurnBatch:
    """One ordered, turn-aligned batch of memory candidates."""

    messages: tuple[Message, ...]
    turn_count: int


class MemoryTurnInputTooLargeError(ValueError):
    """One indivisible turn exceeds an LLM batch's character budget."""

    def __init__(self, *, turn_id: int, character_count: int, limit: int) -> None:
        self.turn_id = int(turn_id)
        self.character_count = int(character_count)
        self.limit = int(limit)
        super().__init__(
            "turn input exceeds batch character limit: "
            f"turn_id={self.turn_id}, characters={self.character_count}, limit={self.limit}"
        )


def batch_memory_turn_groups(
    groups: list[list[Message]],
    *,
    batch_turns: int,
    max_batch_chars: int | None = None,
) -> tuple[MemoryTurnBatch, ...]:
    """Split logical turn groups by count and size without cutting a turn."""
    if isinstance(batch_turns, bool) or not isinstance(batch_turns, int) or batch_turns <= 0:
        raise ValueError("batch_turns must be a positive integer")
    if (
        max_batch_chars is not None
        and (
            isinstance(max_batch_chars, bool)
            or not isinstance(max_batch_chars, int)
            or max_batch_chars <= 0
        )
    ):
        raise ValueError("max_batch_chars must be a positive integer")

    batches: list[MemoryTurnBatch] = []
    batch_groups: list[list[Message]] = []
    batch_chars = 0

    def flush() -> None:
        nonlocal batch_groups, batch_chars
        if not batch_groups:
            return
        batches.append(
            MemoryTurnBatch(
                messages=tuple(
                    message for group in batch_groups for message in group
                ),
                turn_count=len(batch_groups),
            )
        )
        batch_groups = []
        batch_chars = 0

    for group in groups:
        group_chars = sum(len(str(message.content or "")) for message in group)
        if max_batch_chars is not None and group_chars > max_batch_chars:
            turn_id = int(group[0].turn_id) if group else 0
            raise MemoryTurnInputTooLargeError(
                turn_id=turn_id,
                character_count=group_chars,
                limit=max_batch_chars,
            )
        if batch_groups and (
            len(batch_groups) >= batch_turns
            or (
                max_batch_chars is not None
                and batch_chars + group_chars > max_batch_chars
            )
        ):
            flush()
        batch_groups.append(group)
        batch_chars += group_chars
    flush()
    return tuple(batches)


def select_summary_turn_groups(
    session: SessionManager,
    *,
    keep_recent_turns: int,
    mark_excluded: bool = True,
) -> list[list[Message]]:
    """Return eligible IC/GM groups, optionally advancing excluded OOC rows."""
    included, excluded = _partition_mode_groups(session.summary_unprocessed_turn_groups())
    if excluded and mark_excluded:
        session.mark_summary_messages_processed(
            [message for group in excluded for message in group],
            batch_id=None,
        )
    unprocessed_keys = {
        _message_key(message)
        for group in included
        for message in group
    }
    all_conversation = [message for message in session.history if not message.is_system()]
    all_allowed_groups, _ = _partition_mode_groups(
        session.iter_turn_groups(all_conversation)
    )
    keep = max(0, int(keep_recent_turns))
    eligible_groups = all_allowed_groups if keep <= 0 else all_allowed_groups[:-keep]
    return [
        [message for message in group if _message_key(message) in unprocessed_keys]
        for group in eligible_groups
        if any(_message_key(message) in unprocessed_keys for message in group)
    ]


def select_story_memory_turn_groups(
    session: SessionManager,
) -> list[list[Message]]:
    """Mark OOC story-memory rows and return IC/GM extraction groups."""
    included, excluded = _partition_mode_groups(
        session.story_turn_groups_since_last_extraction()
    )
    if excluded:
        session.mark_story_messages_processed(
            [message for group in excluded for message in group]
        )
    return included


def _partition_mode_groups(
    groups: list[list[Message]],
) -> tuple[list[list[Message]], list[list[Message]]]:
    included: list[list[Message]] = []
    excluded: list[list[Message]] = []
    for group in groups:
        modes = {str(message.mode or TurnMode.IC.value).strip().lower() for message in group}
        if TurnMode.OOC.value in modes:
            excluded.append(group)
        elif modes and modes.issubset(_ALLOWED_MEMORY_MODES):
            included.append(group)
        else:
            raise ValueError(f"unsupported message mode(s): {sorted(modes)}")
    return included, excluded


def _message_key(message: Message) -> tuple[str, int]:
    if message.uid > 0:
        return ("uid", message.uid)
    return ("object", id(message))
