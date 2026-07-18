from __future__ import annotations

from rpg_core.session.grouping import (
    select_story_memory_turn_groups,
    select_summary_turn_groups,
)
from rpg_core.context.models import Message, Role
from rpg_core.session.manager import SessionManager


def _turn(turn_id: int, mode: str) -> list[Message]:
    return [
        Message(Role.USER, f"u{turn_id}", mode=mode, turn_id=turn_id, seq_in_turn=1),
        Message(Role.ASSISTANT, f"a{turn_id}", mode=mode, turn_id=turn_id, seq_in_turn=2),
    ]


def test_ooc_is_marked_per_business_flow_and_does_not_consume_keep_window() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        *_turn(1, "ic"),
        *_turn(2, "ooc"),
        *_turn(3, "gm"),
    ], persist=False)

    summary_groups = select_summary_turn_groups(session, keep_recent_turns=1)
    assert [[message.turn_id for message in group] for group in summary_groups] == [[1, 1]]
    assert [message.turn_id for message in session.context_history().messages] == [1, 1, 3, 3]

    story_groups = select_story_memory_turn_groups(session)
    assert [[message.turn_id for message in group] for group in story_groups] == [
        [1, 1],
        [3, 3],
    ]
    assert session.count_new_turns_since_story() == 2


def test_non_contiguous_ooc_markers_remain_restart_cursor_free() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        *_turn(1, "ooc"),
        *_turn(4, "ic"),
        *_turn(9, "ooc"),
        *_turn(12, "gm"),
    ], persist=False)

    assert [group[0].turn_id for group in select_story_memory_turn_groups(session)] == [4, 12]
    assert [group[0].turn_id for group in session.story_turn_groups_since_last_extraction()] == [4, 12]
    assert [group[0].turn_id for group in select_summary_turn_groups(
        session,
        keep_recent_turns=0,
    )] == [4, 12]


def test_summary_keep_window_uses_full_allowed_history_not_only_unprocessed_turns() -> None:
    session = SessionManager(history_enabled=False)
    turns = [message for turn_id in range(1, 5) for message in _turn(turn_id, "ic")]
    session.replace_history(turns, persist=False)
    session.mark_summary_messages_processed(
        [message for message in turns if message.turn_id >= 2],
        batch_id=1,
    )

    groups = select_summary_turn_groups(session, keep_recent_turns=2)

    assert [group[0].turn_id for group in groups] == [1]
