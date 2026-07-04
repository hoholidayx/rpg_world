from __future__ import annotations

import json
from pathlib import Path

import pytest
from peewee import SqliteDatabase

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.repositories.records import (
    SessionBackupMessageRecord,
    SessionMessageRecord,
    SessionRecord,
)
from rpg_data.services.backup import BackupService
from rpg_data.services.message import MessageService
from rpg_data.services.story_memory import StoryMemoryService


def _migrated_database(tmp_path: Path) -> SqliteDatabase:
    db_path = tmp_path / "messages.sqlite3"
    conn = db.connect(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()

    database = db.bind_peewee_database(db.make_peewee_database(db_path))
    database.connect()
    return database


def _create_test_session(database: SqliteDatabase, session_id: str) -> str:
    database.execute_sql(
        """
        INSERT INTO rpg_sessions (id, workspace_id, story_id)
        SELECT ?, 'demo_workspace', id
        FROM rpg_stories
        WHERE workspace_id = 'demo_workspace' AND title = '北境森林 Demo'
        """,
        (session_id,),
    )
    return session_id


def test_message_service_crud_replace_and_truncate(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        backup = BackupService(database)
        session_id = _create_test_session(database, "s_message_crud")

        first = messages.append(session_id, "user", "hello", turn_id=1, seq_in_turn=1)
        second = messages.append(
            session_id,
            "assistant",
            "world",
            turn_id=1,
            seq_in_turn=2,
            tool_calls_json='[{"id":"tc1"}]',
        )

        assert [row.content for row in messages.list(session_id)] == ["hello", "world"]
        assert messages.count(session_id) == 2
        assert not hasattr(first, "hid")
        assert first.to_message_dict()["uid"] == first.id
        assert messages.list(session_id, limit=1, offset=1)[0].id == second.id

        updated = messages.update(second.id, content="updated", tool_call_id="tc1")
        assert updated is not None
        assert updated.content == "updated"
        assert updated.tool_call_id == "tc1"

        mapped = messages.append_mapping(
            session_id,
            {
                "role": "assistant",
                "content": "uses tool",
                "turn_id": 2,
                "seq_in_turn": 1,
                "tool_calls": [{"id": "call_1", "type": "function"}],
            },
        )
        assert json.loads(mapped.tool_calls_json)[0]["id"] == "call_1"

        assert messages.delete(first.id)
        assert messages.get(first.id) is None

        backup.messages.append(session_id, "user", "cold copy", turn_id=1, seq_in_turn=1)
        replacement = messages.replace(
            session_id,
            [
                {"role": "user", "content": "u1", "turn_id": 10, "seq_in_turn": 1},
                {"role": "assistant", "content": "a1", "turn_id": 10, "seq_in_turn": 2},
                {"role": "user", "content": "u2", "turn_id": 11, "seq_in_turn": 1},
            ],
        )

        assert [row.content for row in replacement] == ["u1", "a1", "u2"]
        assert backup.messages.count(session_id) == 1

        assert messages.truncate_before_index(session_id, 1) == 1
        assert [row.content for row in messages.list(session_id)] == ["a1", "u2"]

        boundary_id = messages.list(session_id)[1].id
        assert messages.truncate_before_id(session_id, boundary_id) == 1
        assert [row.content for row in messages.list(session_id)] == ["u2"]

        assert messages.truncate_before_index(session_id, 999) == 1
        assert messages.count(session_id) == 0
        assert backup.messages.count(session_id) == 1

        with pytest.raises(ValueError):
            messages.append(session_id, "bad_role", "invalid")
    finally:
        database.close()


def test_story_memory_service_crud_and_cursor(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        story_memory = StoryMemoryService(database)

        first = story_memory.add_detail("s_forest001", "remember this", turn_id=2)
        second = story_memory.add_detail(
            "s_forest001",
            "dream this",
            turn_id=3,
            dream_processed=True,
            metadata_json='{"kind":"test"}',
        )

        assert [row.text for row in story_memory.list("s_forest001")] == ["remember this", "dream this"]
        assert [row.id for row in story_memory.list("s_forest001", dream_processed=True)] == [second.id]
        assert story_memory.get(first.id).to_context_dict()["turn_id"] == 2
        assert story_memory.get(second.id).to_context_dict()["metadata"] == {"kind": "test"}

        assert story_memory.get_last_turn_id("s_forest001") == 0
        story_memory.set_last_turn_id("s_forest001", 3)
        assert story_memory.get_last_turn_id("s_forest001") == 3

        assert story_memory.set_dream_processed([first.id], dream_processed=True) == 1
        assert {row.id for row in story_memory.list("s_forest001", dream_processed=True)} == {
            first.id,
            second.id,
        }

        replacement = story_memory.set_details(
            "s_forest001",
            [
                {"text": "replacement", "turn_id": 4, "metadata": {"kind": "unit"}},
            ],
        )
        assert [row.text for row in replacement] == ["replacement"]
        assert story_memory.list("s_forest001")[0].to_context_dict()["metadata"] == {"kind": "unit"}
    finally:
        database.close()


def test_message_service_truncate_from_turn_keeps_backup_append_only(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        backup = BackupService(database)
        session_id = _create_test_session(database, "s_message_truncate_from_turn")

        for turn_id, role, content, seq in [
            (1, "user", "u1", 1),
            (1, "assistant", "a1", 2),
            (2, "user", "u2", 1),
            (2, "assistant", "a2", 2),
            (3, "user", "u3", 1),
        ]:
            messages.append(session_id, role, content, turn_id=turn_id, seq_in_turn=seq)
            backup.messages.append(session_id, role, content, turn_id=turn_id, seq_in_turn=seq)

        assert messages.truncate_from_turn(session_id, 2) == 3
        assert [row.content for row in messages.list(session_id)] == ["u1", "a1"]
        assert [row.content for row in backup.messages.list(session_id)] == ["u1", "a1", "u2", "a2", "u3"]
        assert messages.get_for_session(session_id, messages.list(session_id)[0].id).content == "u1"

        with pytest.raises(ValueError):
            messages.truncate_from_turn(session_id, 0)
    finally:
        database.close()


def test_backup_messages_are_append_only_and_independent(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        backup = BackupService(database)
        session_id = _create_test_session(database, "s_message_backup")

        main = messages.append(session_id, "user", "main", turn_id=1, seq_in_turn=1)
        cold = backup.messages.append_mapping(
            session_id,
            {
                "role": "user",
                "content": "main",
                "turn_id": main.turn_id,
                "seq_in_turn": main.seq_in_turn,
            },
        )
        backup.messages.append(session_id, "assistant", "cold-only", turn_id=1, seq_in_turn=2)

        assert [row.content for row in messages.list(session_id)] == ["main"]
        assert [row.content for row in backup.messages.list(session_id)] == ["main", "cold-only"]
        assert backup.messages.get(cold.id).content == "main"
        assert backup.messages.count(session_id) == 2
        assert not hasattr(backup.messages, "delete")
        assert not hasattr(backup.messages, "truncate_before_index")

        SessionRecord.delete().where(SessionRecord.id == session_id).execute()

        assert SessionMessageRecord.select().where(
            SessionMessageRecord.session == session_id
        ).count() == 0
        assert SessionBackupMessageRecord.select().where(
            SessionBackupMessageRecord.session == session_id
        ).count() == 0
    finally:
        database.close()
