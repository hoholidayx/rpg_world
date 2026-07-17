"""Compatibility wrappers around :class:`SessionManager` turn helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from rpg_core.session.grouping import (
    count_turns as count_grouped_turns,
    has_explicit_turn_ids as contains_explicit_turn_ids,
    has_trustworthy_turn_ids as contains_trustworthy_turn_ids,
    iter_turn_groups as group_messages_by_turn,
    latest_turn_id as find_latest_turn_id,
    slice_recent_turns as select_recent_turns,
    split_into_turn_batches as build_turn_batches,
)
from rpg_core.session.turn_metadata import (
    InvalidTurnMetadataError,
    validate_turn_metadata,
)

if TYPE_CHECKING:
    from rpg_core.context.rpg_context import Message


def has_explicit_turn_ids(messages: list[Message]) -> bool:
    return contains_explicit_turn_ids(messages)


def has_trustworthy_turn_ids(messages: list[Message]) -> bool:
    return contains_trustworthy_turn_ids(messages)


def iter_turn_groups(messages: list[Message]) -> list[list[Message]]:
    return group_messages_by_turn(messages)


def count_turns(messages: list[Message]) -> int:
    return count_grouped_turns(messages)


def slice_recent_turns(messages: list[Message], keep_turns: int) -> list[Message]:
    return select_recent_turns(messages, keep_turns)


def split_into_turn_batches(
    messages: list[Message],
    batch_turn_size: int,
) -> list[tuple[int, list[Message], int]]:
    return build_turn_batches(messages, batch_turn_size)


def count_roles(messages: Iterable[Message]) -> dict[str, int]:
    counts = {"system": 0, "user": 0, "assistant": 0, "tool": 0}
    for msg in messages:
        role = msg.role.value
        if role in counts:
            counts[role] += 1
    return counts


def latest_turn_id(messages: list[Message]) -> int:
    return find_latest_turn_id(messages)
