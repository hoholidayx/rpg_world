"""Shared turn grouping and memory-processing candidate selection.

The algorithms in this module operate only on the public ``SessionManager``
surface.  Keeping them in the session domain prevents summary code from
depending on a concrete Agent or SubAgent implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rpg_core.agent.turn.models import TurnMode
from rpg_core.context.models import Message
from rpg_core.session.turn_metadata import has_trustworthy_turn_metadata

if TYPE_CHECKING:
    from rpg_core.session.manager import SessionManager


_ALLOWED_MEMORY_MODES = frozenset({TurnMode.IC.value, TurnMode.GM.value})


def has_explicit_turn_ids(messages: list[Message]) -> bool:
    """Return whether any message carries a positive ``turn_id``."""
    return any(message.turn_id > 0 for message in messages)


def has_trustworthy_turn_ids(messages: list[Message]) -> bool:
    """Return whether explicit turn ids can be used safely."""
    return has_trustworthy_turn_metadata(messages)


def iter_turn_groups(messages: list[Message]) -> list[list[Message]]:
    """Group messages into logical turns without changing their order.

    Trustworthy explicit metadata takes precedence. Legacy prefixes fall back
    to user anchors, or two-message windows when no user anchor exists.
    """
    if not messages:
        return []

    first_explicit = next(
        (
            index
            for index, message in enumerate(messages)
            if message.turn_id > 0 and message.seq_in_turn > 0
        ),
        len(messages),
    )
    if first_explicit < len(messages):
        suffix = messages[first_explicit:]
        if has_trustworthy_turn_ids(suffix):
            return _iter_legacy_groups(messages[:first_explicit]) + _iter_explicit_turn_groups(
                suffix
            )

    return _iter_legacy_groups(messages)


def count_turns(messages: list[Message]) -> int:
    return len(iter_turn_groups(messages))


def slice_recent_turns(messages: list[Message], keep_turns: int) -> list[Message]:
    if keep_turns <= 0:
        return []

    groups = iter_turn_groups(messages)
    if len(groups) <= keep_turns:
        return list(messages)

    return [message for group in groups[-keep_turns:] for message in group]


def split_into_turn_batches(
    messages: list[Message],
    batch_turn_size: int,
) -> list[tuple[int, list[Message], int]]:
    if batch_turn_size <= 0:
        raise ValueError("batch_turn_size must be positive")

    groups = iter_turn_groups(messages)
    if not groups:
        return []

    batches: list[tuple[int, list[Message], int]] = []
    batch_id = 0
    start = 0
    while start < len(groups):
        end = min(start + batch_turn_size, len(groups))
        batch_groups = groups[start:end]
        batch_messages = [message for group in batch_groups for message in group]
        batches.append((batch_id, batch_messages, end - start))
        batch_id += 1
        start = end
    return batches


def latest_turn_id(messages: list[Message]) -> int:
    turn_ids = [message.turn_id for message in messages if message.turn_id > 0]
    return max(turn_ids, default=0)


def uses_fallback_grouping(messages: list[Message]) -> bool:
    if not messages:
        return False
    first_explicit = next(
        (
            index
            for index, message in enumerate(messages)
            if message.turn_id > 0 and message.seq_in_turn > 0
        ),
        len(messages),
    )
    if first_explicit >= len(messages):
        return True
    return first_explicit > 0 or not has_trustworthy_turn_ids(messages[first_explicit:])


def _iter_legacy_groups(messages: list[Message]) -> list[list[Message]]:
    if any(message.is_user() for message in messages):
        return _iter_user_anchor_groups(messages)
    return _iter_pairs(messages)


def _iter_user_anchor_groups(messages: list[Message]) -> list[list[Message]]:
    user_indices = [index for index, message in enumerate(messages) if message.is_user()]
    if not user_indices:
        return _iter_pairs(messages)

    groups: list[list[Message]] = []
    for index, user_index in enumerate(user_indices):
        start = 0 if index == 0 else user_index
        end = user_indices[index + 1] if index + 1 < len(user_indices) else len(messages)
        groups.append(messages[start:end])
    return groups


def _iter_pairs(messages: list[Message]) -> list[list[Message]]:
    if not messages:
        return []
    groups: list[list[Message]] = []
    index = 0
    while index < len(messages):
        groups.append(messages[index:index + 2])
        index += 2
    return groups


def _iter_explicit_turn_groups(messages: list[Message]) -> list[list[Message]]:
    if not messages:
        return []

    groups: list[list[Message]] = []
    current_turn_id = messages[0].turn_id
    current_group: list[Message] = []
    for message in messages:
        if message.turn_id <= 0 or message.seq_in_turn <= 0:
            if current_group:
                groups.append(current_group)
                current_group = []
            groups.append([message])
            continue
        if message.turn_id != current_turn_id and current_group:
            groups.append(current_group)
            current_group = []
        current_turn_id = message.turn_id
        current_group.append(message)
    if current_group:
        groups.append(current_group)
    return groups


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
