from __future__ import annotations

from rpg_world.rpg_core.context.rpg_context import Message, Role
from rpg_world.rpg_core.session.manager import SessionManager


def test_iter_turn_groups_uses_two_message_fallback_without_user_anchor():
    messages = [
        Message(Role.ASSISTANT, "a1"),
        Message(Role.TOOL, "tool1"),
        Message(Role.SYSTEM, "sys1"),
    ]

    groups = SessionManager.iter_turn_groups(messages)

    assert len(groups) == 2
    assert [msg.content for msg in groups[0]] == ["a1", "tool1"]
    assert [msg.content for msg in groups[1]] == ["sys1"]
    assert SessionManager.count_turns(messages) == 2


def test_iter_turn_groups_keeps_single_message_as_one_turn_without_user_anchor():
    messages = [Message(Role.ASSISTANT, "a1")]

    groups = SessionManager.iter_turn_groups(messages)

    assert len(groups) == 1
    assert [msg.content for msg in groups[0]] == ["a1"]
    assert SessionManager.count_turns(messages) == 1


def test_iter_turn_groups_keeps_multi_message_turns_with_explicit_ids():
    messages = [
        Message(Role.SYSTEM, "sys", turn_id=1, seq_in_turn=1),
        Message(Role.USER, "u1", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=2, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=3, seq_in_turn=1),
    ]

    groups = SessionManager.iter_turn_groups(messages)

    assert len(groups) == 3
    assert [msg.content for msg in groups[1]] == ["u1", "a1"]
    assert SessionManager.count_turns(messages) == 3


def test_iter_turn_groups_falls_back_on_invalid_turn_ids():
    messages = [
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=2, seq_in_turn=1),
        Message(Role.USER, "u2", turn_id=1, seq_in_turn=1),
    ]

    groups = SessionManager.iter_turn_groups(messages)

    assert len(groups) == 2
    assert [msg.content for msg in groups[0]] == ["u1", "a1"]
    assert [msg.content for msg in groups[1]] == ["u2"]
    assert SessionManager.count_turns(messages) == 2
