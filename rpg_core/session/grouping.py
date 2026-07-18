"""Generic grouping and inspection helpers for persisted conversation turns."""

from __future__ import annotations

from collections.abc import Iterable

from rpg_core.context.models import Message
from rpg_core.session.turn_metadata import has_trustworthy_turn_metadata


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


def count_roles(messages: Iterable[Message]) -> dict[str, int]:
    counts = {"system": 0, "user": 0, "assistant": 0, "tool": 0}
    for message in messages:
        role = message.role.value
        if role in counts:
            counts[role] += 1
    return counts


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
