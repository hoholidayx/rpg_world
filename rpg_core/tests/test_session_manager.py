from __future__ import annotations

import json

import pytest

from rpg_world.rpg_core.context.rpg_context import Message, Role
from rpg_world.rpg_core.session.manager import SessionManager


@pytest.fixture
def workspace():
    return "data/test_workspace"


def test_validate_session_id():
    assert SessionManager.validate_session_id("abc_123") == "abc_123"
    with pytest.raises(ValueError):
        SessionManager.validate_session_id("bad-id")


def test_create_list_delete_clone_session(temp_settings, workspace):
    SessionManager.create(workspace, "s1")
    SessionManager.create(workspace, "s2")
    assert SessionManager.list_sessions(workspace) == ["s1", "s2"]

    SessionManager.clone(workspace, "s1", "s3")
    assert sorted(SessionManager.list_sessions(workspace)) == ["s1", "s2", "s3"]

    SessionManager.delete(workspace, "s2")
    assert sorted(SessionManager.list_sessions(workspace)) == ["s1", "s3"]


def test_append_persists_history_and_unique_ids(temp_settings, workspace):
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    turn_id = mgr.begin_turn()
    mgr.append(Role.USER, "hello", turn_id=turn_id)
    mgr.append(Role.ASSISTANT, "world", turn_id=turn_id)
    mgr.end_turn(turn_id)

    history_path = temp_settings / workspace / "sessions" / "s1" / "history.jsonl"
    cold_path = temp_settings / workspace / "sessions" / "s1" / "history_cold.jsonl"
    meta_path = temp_settings / workspace / "sessions" / "s1" / "session.json"

    history_rows = history_path.read_text(encoding="utf-8").strip().splitlines()
    cold_rows = cold_path.read_text(encoding="utf-8").strip().splitlines()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert len(history_rows) == 2
    assert len(cold_rows) == 2
    assert json.loads(history_rows[0])["rp_his_id"] != json.loads(history_rows[1])["rp_his_id"]
    assert json.loads(history_rows[0])["turn_id"] == json.loads(history_rows[1])["turn_id"] == turn_id
    assert json.loads(history_rows[0])["seq_in_turn"] == 1
    assert json.loads(history_rows[1])["seq_in_turn"] == 2
    assert meta["last_story_rp_his_id"] == 0
    assert meta["next_turn_id"] == turn_id + 1
    assert mgr.history[0].content == "hello"
    assert mgr.count_new_turns_since_story() == 1

    reloaded = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    reloaded.load()
    assert reloaded.begin_turn() == turn_id + 1


def test_count_new_turns_uses_user_anchor_when_turn_ids_missing(temp_settings, workspace):
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    mgr.append(Role.USER, "u1", turn_id=0)
    mgr.append(Role.ASSISTANT, "a1", turn_id=0)
    mgr.append(Role.ASSISTANT, "tool-like", turn_id=0)

    assert mgr.count_new_turns_since_story() == 1


def test_count_new_turns_falls_back_to_messages_without_user_anchor(temp_settings, workspace):
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    mgr.replace_history([
        Message(Role.ASSISTANT, "a1", rp_his_id=1, turn_id=0, seq_in_turn=0),
        Message(Role.TOOL, "tool1", rp_his_id=2, turn_id=0, seq_in_turn=0),
        Message(Role.SYSTEM, "sys1", rp_his_id=3, turn_id=0, seq_in_turn=0),
    ], persist=False)

    assert mgr.count_new_turns_since_story() == 3


def test_count_new_turns_falls_back_to_messages_for_invalid_turn_ids(temp_settings, workspace):
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()

    mgr.replace_history([
        Message(Role.USER, "u1", rp_his_id=1, turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", rp_his_id=2, turn_id=2, seq_in_turn=1),
        Message(Role.USER, "u2", rp_his_id=3, turn_id=1, seq_in_turn=1),
    ], persist=False)

    assert mgr.count_new_turns_since_story() == 2


def test_rebuild_turn_state_after_history_compaction(temp_settings, workspace):
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
        Message(Role.USER, "u2", rp_his_id=3, turn_id=t2, seq_in_turn=1),
    ], persist=False)

    mgr.append(Role.ASSISTANT, "a2", turn_id=t2)
    t3 = mgr.begin_turn()

    assert mgr.history[-1].seq_in_turn == 2
    assert t3 == t2 + 1


def test_clear_truncate_checkpoint_and_rollback(temp_settings, workspace):
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

    checkpoint = mgr.checkpoint()
    t3 = mgr.begin_turn()
    mgr.append(Role.USER, "temp", turn_id=t3)
    mgr.rollback(checkpoint)
    assert [m.content for m in mgr.history][-1] == "a2"

    removed = mgr.truncate(2)
    assert removed == 2
    assert [m.content for m in mgr.history] == ["u2", "a2"]

    mgr.clear()
    assert mgr.history == []


def test_switch_to_reload_history(temp_settings, workspace):
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()
    mgr.append(Role.USER, "hello")

    other = SessionManager(session_id="s2", workspace=workspace, history_enabled=True)
    other.load()
    other.append(Role.USER, "world")

    mgr.switch_to("s2")
    assert [m.content for m in mgr.history] == ["world"]
    assert mgr.meta["created_at"]


def test_history_snapshot_is_read_only(temp_settings, workspace):
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()
    mgr.append(Role.USER, "hello")

    snapshot = mgr._history
    snapshot.append(Message(Role.ASSISTANT, "mutated"))

    assert [m.content for m in mgr.history] == ["hello"]
    with pytest.raises(AttributeError):
        mgr._history = []  # type: ignore[assignment]
