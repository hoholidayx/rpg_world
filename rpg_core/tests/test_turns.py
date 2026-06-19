from __future__ import annotations

from rpg_world.rpg_core.context.rpg_context import Message, Role
from rpg_world.rpg_core.session.turns import count_turns, iter_turn_groups


def test_iter_turn_groups_falls_back_to_messages_without_user_anchor():
    messages = [
        Message(Role.ASSISTANT, "a1"),
        Message(Role.TOOL, "tool1"),
        Message(Role.SYSTEM, "sys1"),
    ]

    groups = iter_turn_groups(messages)

    assert len(groups) == 3
    assert [group[0].content for group in groups] == ["a1", "tool1", "sys1"]
    assert count_turns(messages) == 3


def test_iter_turn_groups_keeps_multi_message_turns_with_explicit_ids():
    messages = [
        Message(Role.SYSTEM, "sys", turn_id=1, seq_in_turn=1),
        Message(Role.USER, "u1", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=2, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=3, seq_in_turn=1),
    ]

    groups = iter_turn_groups(messages)

    assert len(groups) == 3
    assert [msg.content for msg in groups[1]] == ["u1", "a1"]
    assert count_turns(messages) == 3


def test_iter_turn_groups_falls_back_on_invalid_turn_ids():
    messages = [
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=2, seq_in_turn=1),
        Message(Role.USER, "u2", turn_id=1, seq_in_turn=1),
    ]

    groups = iter_turn_groups(messages)

    assert len(groups) == 2
    assert [msg.content for msg in groups[0]] == ["u1", "a1"]
    assert [msg.content for msg in groups[1]] == ["u2"]
    assert count_turns(messages) == 2
