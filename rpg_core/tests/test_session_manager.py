from __future__ import annotations

import pytest

from rpg_core.context.rpg_context import Message, Role
from rpg_core.session.manager import SessionManager
from rpg_core.session.turn_metadata import InvalidTurnMetadataError


class _HistoryRow:
    def __init__(self, *, role: str, content: str, turn_id: int, seq_in_turn: int, uid: int) -> None:
        self.role = role
        self.content = content
        self.turn_id = turn_id
        self.seq_in_turn = seq_in_turn
        self.id = uid

    def to_message_dict(self) -> dict[str, object]:
        return {
            "uid": self.id,
            "role": self.role,
            "content": self.content,
            "turn_id": self.turn_id,
            "seq_in_turn": self.seq_in_turn,
        }


@pytest.fixture
def workspace():
    return "data/test_workspace"


def test_validate_session_id():
    assert SessionManager.validate_session_id("abc_123") == "abc_123"
    with pytest.raises(ValueError):
        SessionManager.validate_session_id("bad-id")


def test_load_requires_rpg_data_session(rpg_data_gateway):  # noqa: ARG001
    mgr = SessionManager(session_id="missing_session", history_enabled=True)

    with pytest.raises(FileNotFoundError):
        mgr.load()


def test_load_rejects_invalid_persisted_turn_metadata(monkeypatch):
    class FakeMessages:
        @staticmethod
        def list(_session_id: str):
            return [
                _HistoryRow(role="user", content="u1", turn_id=1, seq_in_turn=1, uid=1),
                _HistoryRow(role="assistant", content="bad", turn_id=1, seq_in_turn=0, uid=2),
            ]

    class FakeGateway:
        messages = FakeMessages()

    mgr = SessionManager(session_id="s_bad_history", history_enabled=True)
    monkeypatch.setattr(mgr, "_require_data_session", lambda: FakeGateway())

    with pytest.raises(InvalidTurnMetadataError, match=r"history\[1\]"):
        mgr.load()

    assert mgr.history == []


def test_append_persists_messages_backup_and_unique_uids(
    make_data_session,
    rpg_data_gateway,
    workspace,
):
    make_data_session("s1")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    turn_id = mgr.begin_turn()
    mgr.append(Role.USER, "hello", turn_id=turn_id)
    mgr.append(Role.ASSISTANT, "world", turn_id=turn_id)
    mgr.end_turn(turn_id)

    main_rows = rpg_data_gateway.messages.list("s1")
    backup_rows = rpg_data_gateway.backup.messages.list("s1")

    assert [row.content for row in main_rows] == ["hello", "world"]
    assert [row.content for row in backup_rows] == ["hello", "world"]
    assert [row.id for row in main_rows] == [message.uid for message in mgr.history]
    assert main_rows[0].id != main_rows[1].id
    assert [row.turn_id for row in main_rows] == [turn_id, turn_id]
    assert [row.seq_in_turn for row in main_rows] == [1, 2]
    assert mgr.count_new_turns_since_story() == 1

    reloaded = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    reloaded.load()
    assert [message.uid for message in reloaded.history] == [row.id for row in main_rows]
    assert reloaded.begin_turn() == turn_id + 1


def test_context_history_filters_processed_rows_without_changing_full_history(
    make_data_session,
    rpg_data_gateway,
    workspace,
):
    make_data_session("s1")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    turn_id = mgr.begin_turn()
    mgr.append(Role.USER, "u1", turn_id=turn_id)
    mgr.append(Role.ASSISTANT, "a1", turn_id=turn_id)
    mgr.end_turn(turn_id)
    user_message = next(message for message in mgr.history if message.is_user())
    rpg_data_gateway.messages.mark_summary_processed(
        "s1",
        [user_message.uid],
        batch_id=99,
    )

    projected = mgr.context_history()

    assert [message.content for message in mgr.history] == ["u1", "a1"]
    assert [message.content for message in projected.messages] == ["a1"]
    assert projected.filtered_message_count == 1


def test_story_memory_progress_uses_message_flags(make_data_session, workspace):
    make_data_session("s1")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    t1 = mgr.begin_turn()
    mgr.append(Role.USER, "u1", turn_id=t1)
    mgr.append(Role.ASSISTANT, "a1", turn_id=t1)
    mgr.end_turn(t1)
    t2 = mgr.begin_turn()
    mgr.append(Role.USER, "u2", turn_id=t2)
    mgr.append(Role.ASSISTANT, "a2", turn_id=t2)
    mgr.end_turn(t2)

    mgr.mark_story_messages_processed(mgr.turn_messages(t1))

    assert [m.content for m in mgr.story_messages_since_last_extraction()] == ["u2", "a2"]
    assert mgr.count_new_turns_since_story() == 1

    mgr.mark_story_messages_processed(mgr.story_messages_since_last_extraction())
    assert mgr.story_messages_since_last_extraction() == []
    assert mgr.count_new_turns_since_story() == 0


def test_iter_turn_groups_uses_two_message_fallback_without_user_anchor():
    messages = [
        Message(Role.ASSISTANT, "a1", uid=1, turn_id=0, seq_in_turn=0),
        Message(Role.TOOL, "tool1", uid=2, turn_id=0, seq_in_turn=0),
        Message(Role.SYSTEM, "sys1", uid=3, turn_id=0, seq_in_turn=0),
    ]

    assert [
        [message.content for message in group]
        for group in SessionManager.iter_turn_groups(messages)
    ] == [["a1", "tool1"], ["sys1"]]


def test_iter_turn_groups_uses_single_message_fallback_without_user_anchor():
    messages = [
        Message(Role.ASSISTANT, "a1", uid=1, turn_id=0, seq_in_turn=0),
    ]

    assert [
        [message.content for message in group]
        for group in SessionManager.iter_turn_groups(messages)
    ] == [["a1"]]


def test_message_from_dict_ignores_legacy_hid_key():
    msg = Message.from_dict({"role": "user", "content": "hello", "hid": 123})

    assert msg.uid == 0
    assert msg.to_dict() == {"role": "user", "content": "hello"}


def test_story_memory_progress_survives_restart(make_data_session, workspace):
    make_data_session("s1")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    t1 = mgr.begin_turn()
    mgr.append(Role.USER, "u1", turn_id=t1)
    mgr.append(Role.ASSISTANT, "a1", turn_id=t1)
    mgr.end_turn(t1)
    t2 = mgr.begin_turn()
    mgr.append(Role.USER, "u2", turn_id=t2)
    mgr.append(Role.ASSISTANT, "a2", turn_id=t2)
    mgr.end_turn(t2)
    mgr.mark_story_messages_processed(mgr.turn_messages(t1))

    reloaded = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    reloaded.load()

    assert [m.content for m in reloaded.story_messages_since_last_extraction()] == ["u2", "a2"]
    assert reloaded.count_new_turns_since_story() == 1

    reloaded.mark_story_messages_processed(reloaded.story_messages_since_last_extraction())
    assert reloaded.story_messages_since_last_extraction() == []


def test_rebuild_turn_state_after_history_compaction(make_data_session, workspace):
    make_data_session("s1")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    t1 = mgr.begin_turn()
    mgr.append(Role.USER, "u1", turn_id=t1)
    mgr.append(Role.ASSISTANT, "a1", turn_id=t1)
    mgr.end_turn(t1)

    t2 = mgr.begin_turn()
    mgr.append(Role.USER, "u2", turn_id=t2)
    mgr.append(Role.ASSISTANT, "a2", turn_id=t2)
    mgr.end_turn(t2)

    mgr.replace_history([
        Message(Role.USER, "u2", turn_id=t2, seq_in_turn=1),
    ], persist=True)

    mgr.append(Role.ASSISTANT, "a2", turn_id=t2)
    t3 = mgr.begin_turn()

    assert mgr.history[-1].seq_in_turn == 2
    assert t3 == t2 + 1


def test_clear_and_truncate_update_main_history_only(
    make_data_session,
    rpg_data_gateway,
    workspace,
):
    make_data_session("s1")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()
    t1 = mgr.begin_turn()
    mgr.append(Role.USER, "u1", turn_id=t1)
    mgr.append(Role.ASSISTANT, "a1", turn_id=t1)
    mgr.end_turn(t1)
    t2 = mgr.begin_turn()
    mgr.append(Role.USER, "u2", turn_id=t2)
    mgr.append(Role.ASSISTANT, "a2", turn_id=t2)
    mgr.end_turn(t2)

    assert rpg_data_gateway.backup.messages.count("s1") == 4

    removed = mgr.truncate(2)
    assert removed == 2
    assert [m.content for m in mgr.history] == ["u2", "a2"]
    assert [row.content for row in rpg_data_gateway.messages.list("s1")] == ["u2", "a2"]
    assert rpg_data_gateway.backup.messages.count("s1") == 4

    mgr.clear()
    assert mgr.history == []
    assert rpg_data_gateway.messages.count("s1") == 0
    assert rpg_data_gateway.backup.messages.count("s1") == 4


def test_history_mutations_reload_and_reset_processing_flags(
    make_data_session,
    rpg_data_gateway,
    workspace,
):
    make_data_session("s1")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    t1 = mgr.begin_turn()
    mgr.append(Role.USER, "u1", turn_id=t1)
    mgr.append(Role.ASSISTANT, "a1", turn_id=t1)
    mgr.end_turn(t1)
    t2 = mgr.begin_turn()
    mgr.append(Role.USER, "u2", turn_id=t2)
    mgr.append(Role.ASSISTANT, "a2", turn_id=t2)
    mgr.end_turn(t2)
    t3 = mgr.begin_turn()
    mgr.append(Role.USER, "u3", turn_id=t3)
    mgr.end_turn(t3)
    mgr.mark_story_messages_processed(mgr.story_messages_since_last_extraction())
    assert mgr.count_new_turns_since_story() == 0

    second_turn_user = next(message for message in mgr.history if message.content == "u2")
    updated = mgr.update_message_content(second_turn_user.uid, "u2 edited")
    assert updated.content == "u2 edited"
    assert [message.content for message in mgr.history] == ["u1", "a1", "u2 edited", "a2", "u3"]
    assert [message.content for message in mgr.story_messages_since_last_extraction()] == ["u2 edited"]

    deleted = mgr.delete_message(next(message.uid for message in mgr.history if message.content == "a2"))
    assert deleted.content == "a2"
    assert [message.content for message in mgr.history] == ["u1", "a1", "u2 edited", "u3"]
    assert rpg_data_gateway.backup.messages.count("s1") == 5
    assert [message.content for message in mgr.story_messages_since_last_extraction()] == ["u2 edited"]

    removed = mgr.truncate_from_turn(t2)
    assert removed == 2
    assert [message.content for message in mgr.history] == ["u1", "a1"]
    assert [row.content for row in rpg_data_gateway.messages.list("s1")] == ["u1", "a1"]
    assert rpg_data_gateway.backup.messages.count("s1") == 5
    assert mgr.story_messages_since_last_extraction() == []


def test_switch_to_reload_history(make_data_session, workspace):
    make_data_session("s1")
    make_data_session("s2")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()
    mgr.append(Role.USER, "hello")

    other = SessionManager(session_id="s2", workspace=workspace, history_enabled=True)
    other.load()
    other.append(Role.USER, "world")

    mgr.switch_to("s2")
    assert [m.content for m in mgr.history] == ["world"]
    assert "story_memory_last_turn_id" not in mgr.meta


def test_history_snapshot_is_read_only(make_data_session, workspace):
    make_data_session("s1")
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()
    mgr.append(Role.USER, "hello")

    snapshot = mgr._history
    snapshot.append(Message(Role.ASSISTANT, "mutated"))

    assert [m.content for m in mgr.history] == ["hello"]
    with pytest.raises(AttributeError):
        mgr._history = []  # type: ignore[assignment]
