"""Turn indexing helpers for conversation history.

The repository historically treated a "round" as "one user message".  That
breaks once a single agent turn can contain multiple user, assistant, tool, or
system messages.  These helpers centralize the turn-based interpretation so the
rest of the codebase can share one definition.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_world.rpg_core.context.rpg_context import Message


def has_explicit_turn_ids(messages: list[Message]) -> bool:
    """Return whether any message already carries a persisted turn id."""
    return any(msg.turn_id > 0 for msg in messages)


def has_trustworthy_turn_ids(messages: list[Message]) -> bool:
    """Return whether the history can safely be grouped by explicit turn ids.

    The explicit id path is only trustworthy when every message has a positive
    ``turn_id``/``seq_in_turn`` and turn ids never go backwards. Otherwise we
    fall back to message-level grouping so that malformed history never drops
    content.
    """
    if not messages:
        return False
    if any(msg.turn_id <= 0 or msg.seq_in_turn <= 0 for msg in messages):
        return False

    last_turn_id = 0
    for msg in messages:
        if msg.turn_id < last_turn_id:
            return False
        last_turn_id = msg.turn_id
    return True


def iter_turn_groups(messages: list[Message]) -> list[list[Message]]:
    """Group messages into turn-sized chunks.

    Modern histories are grouped by explicit ``turn_id``.  Legacy histories
    without trustworthy turn ids fall back to ``user`` anchors first, then
    message-level grouping so that malformed histories never skip content.
    """
    if not messages:
        return []

    if has_trustworthy_turn_ids(messages):
        return _iter_mixed_turn_groups(messages)

    if any(msg.is_user() for msg in messages):
        return _iter_user_anchor_groups(messages)

    return [[msg] for msg in messages]


def count_turns(messages: list[Message]) -> int:
    """Count logical turns in *messages*."""
    return len(iter_turn_groups(messages))


def slice_recent_turns(messages: list[Message], keep_turns: int) -> list[Message]:
    """Keep only the most recent *keep_turns* turns from *messages*."""
    if keep_turns <= 0:
        return []

    groups = iter_turn_groups(messages)
    if len(groups) <= keep_turns:
        return list(messages)

    return [msg for group in groups[-keep_turns:] for msg in group]


def split_into_turn_batches(
    messages: list[Message],
    batch_turn_size: int,
) -> list[tuple[int, list[Message], int]]:
    """Split *messages* into batches of turns.

    Returns ``(batch_id, batch_messages, turn_count)`` tuples.
    """
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
        batch_messages = [msg for group in batch_groups for msg in group]
        batches.append((batch_id, batch_messages, end - start))
        batch_id += 1
        start = end
    return batches


def count_roles(messages: Iterable[Message]) -> dict[str, int]:
    """Count messages by role string."""
    counts = {"system": 0, "user": 0, "assistant": 0, "tool": 0}
    for msg in messages:
        role = msg.role.value
        if role in counts:
            counts[role] += 1
    return counts


def latest_turn_id(messages: list[Message]) -> int:
    """Return the latest explicit turn id, or ``0`` if none exists."""
    turn_ids = [msg.turn_id for msg in messages if msg.turn_id > 0]
    return max(turn_ids, default=0)


def _iter_user_anchor_groups(messages: list[Message]) -> list[list[Message]]:
    user_indices = [i for i, msg in enumerate(messages) if msg.is_user()]
    if not user_indices:
        return [[msg] for msg in messages] if messages else []

    groups: list[list[Message]] = []
    for idx, user_idx in enumerate(user_indices):
        start = 0 if idx == 0 else user_idx
        end = user_indices[idx + 1] if idx + 1 < len(user_indices) else len(messages)
        groups.append(messages[start:end])
    return groups


def _iter_mixed_turn_groups(messages: list[Message]) -> list[list[Message]]:
    """Group a history that mixes legacy and explicit turn ids.

    The transition path is expected to be "old prefix without turn ids" followed
    by "new suffix with explicit turn ids".  We keep the prefix on the user
    anchor rule and then group the modern suffix by turn id.
    """
    first_explicit = next((i for i, msg in enumerate(messages) if msg.turn_id > 0), len(messages))
    legacy_prefix = _iter_user_anchor_groups(messages[:first_explicit])

    groups: list[list[Message]] = list(legacy_prefix)
    if first_explicit >= len(messages):
        return groups

    current_turn_id = messages[first_explicit].turn_id
    current_group: list[Message] = []
    for msg in messages[first_explicit:]:
        if msg.turn_id <= 0:
            groups.append([msg])
            continue
        if msg.turn_id != current_turn_id and current_group:
            groups.append(current_group)
            current_group = []
        current_turn_id = msg.turn_id
        current_group.append(msg)
    if current_group:
        groups.append(current_group)
    return groups
