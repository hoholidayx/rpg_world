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

    mgr.append(Role.USER, "hello")
    mgr.append(Role.ASSISTANT, "world")

    history_path = temp_settings / workspace / "sessions" / "s1" / "history.jsonl"
    cold_path = temp_settings / workspace / "sessions" / "s1" / "history_cold.jsonl"
    meta_path = temp_settings / workspace / "sessions" / "s1" / "session.json"

    history_rows = history_path.read_text(encoding="utf-8").strip().splitlines()
    cold_rows = cold_path.read_text(encoding="utf-8").strip().splitlines()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert len(history_rows) == 2
    assert len(cold_rows) == 2
    assert json.loads(history_rows[0])["rp_his_id"] != json.loads(history_rows[1])["rp_his_id"]
    assert meta["last_story_rp_his_id"] == 0
    assert mgr.history[0].content == "hello"


def test_clear_truncate_checkpoint_and_rollback(temp_settings, workspace):
    mgr = SessionManager(session_id="s1", workspace=workspace, history_enabled=True)
    mgr.load()
    mgr.append(Role.USER, "u1")
    mgr.append(Role.ASSISTANT, "a1")
    mgr.append(Role.USER, "u2")
    mgr.append(Role.ASSISTANT, "a2")

    checkpoint = mgr.checkpoint()
    mgr.append(Role.USER, "temp")
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
