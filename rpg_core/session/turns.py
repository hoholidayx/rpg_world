"""Compatibility wrappers around :class:`SessionManager` turn helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_world.rpg_core.context.rpg_context import Message


def has_explicit_turn_ids(messages: list[Message]) -> bool:
    from rpg_world.rpg_core.session.manager import SessionManager

    return SessionManager.has_explicit_turn_ids(messages)


def has_trustworthy_turn_ids(messages: list[Message]) -> bool:
    from rpg_world.rpg_core.session.manager import SessionManager

    return SessionManager.has_trustworthy_turn_ids(messages)


def iter_turn_groups(messages: list[Message]) -> list[list[Message]]:
    from rpg_world.rpg_core.session.manager import SessionManager

    return SessionManager.iter_turn_groups(messages)


def count_turns(messages: list[Message]) -> int:
    from rpg_world.rpg_core.session.manager import SessionManager

    return SessionManager.count_turns(messages)


def slice_recent_turns(messages: list[Message], keep_turns: int) -> list[Message]:
    from rpg_world.rpg_core.session.manager import SessionManager

    return SessionManager.slice_recent_turns(messages, keep_turns)


def split_into_turn_batches(
    messages: list[Message],
    batch_turn_size: int,
) -> list[tuple[int, list[Message], int]]:
    from rpg_world.rpg_core.session.manager import SessionManager

    return SessionManager.split_into_turn_batches(messages, batch_turn_size)


def count_roles(messages: Iterable[Message]) -> dict[str, int]:
    counts = {"system": 0, "user": 0, "assistant": 0, "tool": 0}
    for msg in messages:
        role = msg.role.value
        if role in counts:
            counts[role] += 1
    return counts


def latest_turn_id(messages: list[Message]) -> int:
    from rpg_world.rpg_core.session.manager import SessionManager

    return SessionManager.latest_turn_id(messages)
