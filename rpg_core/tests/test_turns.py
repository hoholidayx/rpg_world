from __future__ import annotations

import pytest

from rpg_core.context.rpg_context import Message, Role
from rpg_core.session.manager import SessionManager
from rpg_core.session.turn_metadata import InvalidTurnMetadataError, validate_turn_metadata


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


def test_validate_turn_metadata_rejects_invalid_explicit_ids():
    messages = [
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=0),
    ]

    with pytest.raises(InvalidTurnMetadataError, match=r"history\[1\]"):
        validate_turn_metadata(messages, label="history")


def test_validate_turn_metadata_rejects_missing_mapping_keys():
    records = [
        {"messageId": 1, "role": "user", "content": "u1"},
    ]

    with pytest.raises(InvalidTurnMetadataError, match=r"history\[0\]"):
        validate_turn_metadata(records, label="history")


def test_validate_turn_metadata_rejects_nonmonotonic_turn_ids():
    messages = [
        Message(Role.USER, "u1", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
    ]

    with pytest.raises(InvalidTurnMetadataError, match="turn_id must be nondecreasing"):
        SessionManager.validate_turn_metadata(messages, label="history")


def test_validate_turn_metadata_rejects_duplicate_seq_in_turn():
    messages = [
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=1),
    ]

    with pytest.raises(InvalidTurnMetadataError, match="seq_in_turn must increase"):
        validate_turn_metadata(messages, label="history")


def test_append_rejects_duplicate_seq_in_turn_before_mutating_history():
    session = SessionManager(history_enabled=False)
    turn_id = session.begin_turn()
    session.append(Role.USER, "u1", turn_id=turn_id, seq_in_turn=1)

    with pytest.raises(InvalidTurnMetadataError, match="seq_in_turn must increase"):
        session.append(Role.ASSISTANT, "a1", turn_id=turn_id, seq_in_turn=1)

    assert [message.content for message in session.history] == ["u1"]
