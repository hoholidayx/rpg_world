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


def test_message_service_crud_replace_and_truncate(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        backup = BackupService(database)

        first = messages.append("s_forest001", "user", "hello", turn_id=1, seq_in_turn=1)
        second = messages.append(
            "s_forest001",
            "assistant",
            "world",
            turn_id=1,
            seq_in_turn=2,
            tool_calls_json='[{"id":"tc1"}]',
        )

        assert [row.content for row in messages.list("s_forest001")] == ["hello", "world"]
        assert messages.count("s_forest001") == 2
        assert not hasattr(first, "hid")
        assert first.to_message_dict()["uid"] == first.id
        assert messages.list("s_forest001", limit=1, offset=1)[0].id == second.id

        updated = messages.update(second.id, content="updated", tool_call_id="tc1")
        assert updated is not None
        assert updated.content == "updated"
        assert updated.tool_call_id == "tc1"

        mapped = messages.append_mapping(
            "s_forest001",
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

        backup.messages.append("s_forest001", "user", "cold copy", turn_id=1, seq_in_turn=1)
        replacement = messages.replace(
            "s_forest001",
            [
                {"role": "user", "content": "u1", "turn_id": 10, "seq_in_turn": 1},
                {"role": "assistant", "content": "a1", "turn_id": 10, "seq_in_turn": 2},
                {"role": "user", "content": "u2", "turn_id": 11, "seq_in_turn": 1},
            ],
        )

        assert [row.content for row in replacement] == ["u1", "a1", "u2"]
        assert backup.messages.count("s_forest001") == 1

        assert messages.truncate_before_index("s_forest001", 1) == 1
        assert [row.content for row in messages.list("s_forest001")] == ["a1", "u2"]

        boundary_id = messages.list("s_forest001")[1].id
        assert messages.truncate_before_id("s_forest001", boundary_id) == 1
        assert [row.content for row in messages.list("s_forest001")] == ["u2"]

        assert messages.truncate_before_index("s_forest001", 999) == 1
        assert messages.count("s_forest001") == 0
        assert backup.messages.count("s_forest001") == 1

        with pytest.raises(ValueError):
            messages.append("s_forest001", "bad_role", "invalid")
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


def test_backup_messages_are_append_only_and_independent(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        backup = BackupService(database)

        main = messages.append("s_forest001", "user", "main", turn_id=1, seq_in_turn=1)
        cold = backup.messages.append_mapping(
            "s_forest001",
            {
                "role": "user",
                "content": "main",
                "turn_id": main.turn_id,
                "seq_in_turn": main.seq_in_turn,
            },
        )
        backup.messages.append("s_forest001", "assistant", "cold-only", turn_id=1, seq_in_turn=2)

        assert [row.content for row in messages.list("s_forest001")] == ["main"]
        assert [row.content for row in backup.messages.list("s_forest001")] == ["main", "cold-only"]
        assert backup.messages.get(cold.id).content == "main"
        assert backup.messages.count("s_forest001") == 2
        assert not hasattr(backup.messages, "delete")
        assert not hasattr(backup.messages, "truncate_before_index")

        SessionRecord.delete().where(SessionRecord.id == "s_forest001").execute()

        assert SessionMessageRecord.select().where(
            SessionMessageRecord.session == "s_forest001"
        ).count() == 0
        assert SessionBackupMessageRecord.select().where(
            SessionBackupMessageRecord.session == "s_forest001"
        ).count() == 0
    finally:
        database.close()
