from __future__ import annotations

import json
from pathlib import Path

import pytest
from peewee import SqliteDatabase

from commons.errors import InvalidTurnMetadataError
from rpg_data import db, models
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

        first = messages.append(session_id, models.MESSAGE_ROLE_USER, "hello", turn_id=1, seq_in_turn=1)
        second = messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
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
                "role": models.MESSAGE_ROLE_ASSISTANT,
                "content": "uses tool",
                "turn_id": 2,
                "seq_in_turn": 1,
                "tool_calls": [{"id": "call_1", "type": "function"}],
            },
        )
        assert json.loads(mapped.tool_calls_json)[0]["id"] == "call_1"

        assert messages.delete(first.id)
        assert messages.get(first.id) is None

        backup.messages.append(session_id, models.MESSAGE_ROLE_USER, "cold copy", turn_id=1, seq_in_turn=1)
        replacement = messages.replace(
            session_id,
            [
                {"role": models.MESSAGE_ROLE_USER, "content": "u1", "turn_id": 10, "seq_in_turn": 1},
                {"role": models.MESSAGE_ROLE_ASSISTANT, "content": "a1", "turn_id": 10, "seq_in_turn": 2},
                {"role": models.MESSAGE_ROLE_USER, "content": "u2", "turn_id": 11, "seq_in_turn": 1},
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


def test_message_service_turn_window_pagination(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        session_id = _create_test_session(database, "s_message_turn_window")

        for turn_id in range(1, 6):
            messages.append(session_id, models.MESSAGE_ROLE_USER, f"u{turn_id}", turn_id=turn_id, seq_in_turn=1)
            messages.append(session_id, models.MESSAGE_ROLE_ASSISTANT, f"a{turn_id}", turn_id=turn_id, seq_in_turn=2)

        latest = messages.list_turn_window(session_id, limit=2)
        before = messages.list_turn_window(session_id, limit=2, before_turn_id=4)
        after = messages.list_turn_window(session_id, limit=2, after_turn_id=2)

        assert [(row.turn_id, row.content) for row in latest] == [
            (4, "u4"),
            (4, "a4"),
            (5, "u5"),
            (5, "a5"),
        ]
        assert [(row.turn_id, row.content) for row in before] == [
            (2, "u2"),
            (2, "a2"),
            (3, "u3"),
            (3, "a3"),
        ]
        assert [(row.turn_id, row.content) for row in after] == [
            (3, "u3"),
            (3, "a3"),
            (4, "u4"),
            (4, "a4"),
        ]
        assert messages.has_turn_before(session_id, 2)
        assert not messages.has_turn_before(session_id, 1)
        assert messages.has_turn_after(session_id, 4)
        assert not messages.has_turn_after(session_id, 5)

        empty_session_id = _create_test_session(database, "s_message_turn_window_empty")
        assert messages.list_turn_window(empty_session_id, limit=50) == []
        assert messages.latest_turn_id(empty_session_id) == 0
    finally:
        database.close()


def test_message_service_requires_valid_turn_metadata(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        backup = BackupService(database)
        session_id = _create_test_session(database, "s_message_turn_constraints")

        messages.append(session_id, models.MESSAGE_ROLE_USER, "u1", turn_id=1, seq_in_turn=1)

        for kwargs in (
            {},
            {"turn_id": 0, "seq_in_turn": 1},
            {"turn_id": 1, "seq_in_turn": 0},
            {"turn_id": -1, "seq_in_turn": 1},
        ):
            with pytest.raises(InvalidTurnMetadataError):
                messages.append(session_id, models.MESSAGE_ROLE_USER, "invalid", **kwargs)
            with pytest.raises(InvalidTurnMetadataError):
                backup.messages.append(session_id, models.MESSAGE_ROLE_USER, "invalid", **kwargs)

        with pytest.raises(InvalidTurnMetadataError):
            messages.append(session_id, models.MESSAGE_ROLE_ASSISTANT, "duplicate seq", turn_id=1, seq_in_turn=1)

        backup.messages.append(session_id, models.MESSAGE_ROLE_USER, "cold 1", turn_id=1, seq_in_turn=1)
        backup.messages.append(session_id, models.MESSAGE_ROLE_USER, "cold 1 retry", turn_id=1, seq_in_turn=1)
        assert [row.content for row in backup.messages.list(session_id)] == ["cold 1", "cold 1 retry"]
    finally:
        database.close()


def test_message_service_replace_validates_before_clear(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        session_id = _create_test_session(database, "s_message_replace_invalid")
        messages.append(session_id, models.MESSAGE_ROLE_USER, "kept", turn_id=1, seq_in_turn=1)

        with pytest.raises(InvalidTurnMetadataError):
            messages.replace(
                session_id,
                [
                    {"role": models.MESSAGE_ROLE_USER, "content": "invalid"},
                ],
            )

        assert [row.content for row in messages.list(session_id)] == ["kept"]
    finally:
        database.close()


def test_story_memory_service_crud(tmp_path: Path) -> None:
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

        with pytest.raises(InvalidTurnMetadataError):
            story_memory.add_detail("s_forest001", "missing turn", turn_id=0)
        with pytest.raises(InvalidTurnMetadataError):
            story_memory.set_details("s_forest001", [{"text": "invalid"}])
        assert [row.text for row in story_memory.list("s_forest001")] == ["replacement"]
    finally:
        database.close()


def test_message_service_processing_flags(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        backup = BackupService(database)
        session_id = _create_test_session(database, "s_message_processing_flags")

        rows = []
        for turn_id, role, content, seq in [
            (1, models.MESSAGE_ROLE_USER, "u1", 1),
            (1, models.MESSAGE_ROLE_ASSISTANT, "a1", 2),
            (2, models.MESSAGE_ROLE_USER, "u2", 1),
            (2, models.MESSAGE_ROLE_ASSISTANT, "a2", 2),
            (3, models.MESSAGE_ROLE_USER, "u3", 1),
            (3, models.MESSAGE_ROLE_ASSISTANT, "a3", 2),
        ]:
            rows.append(messages.append(session_id, role, content, turn_id=turn_id, seq_in_turn=seq))
            backup.messages.append(session_id, role, content, turn_id=turn_id, seq_in_turn=seq)

        assert [
            [row.content for row in group]
            for group in messages.list_summary_candidate_turn_groups(session_id, keep_recent_turns=1)
        ] == [["u1", "a1"], ["u2", "a2"]]
        assert messages.count_summary_candidate_turns(session_id, keep_recent_turns=1) == 2

        first_turn_ids = [row.id for row in rows[:2]]
        assert messages.mark_summary_processed(session_id, first_turn_ids, batch_id=7) == 2
        marked = [messages.get(row_id) for row_id in first_turn_ids]
        assert all(row is not None and row.summary_processed for row in marked)
        assert {row.summary_batch_id for row in marked if row is not None} == {7}
        assert messages.list_summary_turn_ranges(session_id) == {7: (1, 1)}
        assert [
            [row.content for row in group]
            for group in messages.list_summary_candidate_turn_groups(session_id, keep_recent_turns=1)
        ] == [["u2", "a2"]]

        assert messages.count_story_memory_unprocessed_turns(session_id) == 3
        assert messages.mark_story_memory_processed(session_id, [row.id for row in rows[:4]]) == 4
        assert [
            [row.content for row in group]
            for group in messages.list_story_memory_unprocessed_turn_groups(session_id)
        ] == [["u3", "a3"]]

        updated = messages.update(first_turn_ids[0], content="u1 edited")
        assert updated is not None
        assert updated.content == "u1 edited"
        edited = messages.get(first_turn_ids[0])
        untouched = messages.get(first_turn_ids[1])
        assert edited is not None and not edited.summary_processed
        assert edited.summary_batch_id is None
        assert not edited.story_memory_processed
        assert untouched is not None and untouched.summary_processed
        assert untouched.summary_batch_id == 7
        assert untouched.story_memory_processed
        assert messages.list_summary_turn_ranges(session_id) == {7: (1, 1)}

        cold = backup.messages.list(session_id)[0]
        assert cold.summary_processed is False
        assert cold.story_memory_processed is False
    finally:
        database.close()


def test_agent_context_projection_uses_summary_processed_only(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        session_id = _create_test_session(database, "s_message_context_projection")
        first_user = messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "u1",
            turn_id=1,
            seq_in_turn=1,
        )
        first_assistant = messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "a1",
            turn_id=1,
            seq_in_turn=2,
        )
        second_user = messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "u2",
            turn_id=2,
            seq_in_turn=1,
        )

        messages.mark_summary_processed(session_id, [first_user.id], batch_id=7)
        (
            SessionMessageRecord
            .update(summary_batch_id=None)
            .where(SessionMessageRecord.id == first_user.id)
            .execute()
        )

        projection = messages.list_for_agent_context(session_id)

        assert [row.content for row in messages.list(session_id)] == ["u1", "a1", "u2"]
        assert [row.content for row in projection.messages] == ["a1", "u2"]
        assert projection.filtered_message_count == 1
        assert first_assistant.summary_processed is False
        assert second_user.summary_processed is False

        assert messages.delete_for_session(session_id, first_user.id) is True
        after_delete = messages.list_for_agent_context(session_id)
        assert [row.content for row in after_delete.messages] == ["a1", "u2"]
        assert after_delete.filtered_message_count == 0
    finally:
        database.close()


def test_message_service_rejects_turn_metadata_update(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        session_id = _create_test_session(database, "s_message_turn_update")
        row = messages.append(session_id, models.MESSAGE_ROLE_USER, "u1", turn_id=1, seq_in_turn=1)

        with pytest.raises(InvalidTurnMetadataError):
            messages.update(row.id, turn_id=2)
        with pytest.raises(InvalidTurnMetadataError):
            messages.update(row.id, seq_in_turn=2)
        assert messages.get(row.id).turn_id == 1
        assert messages.get(row.id).seq_in_turn == 1
    finally:
        database.close()


def test_summary_candidates_keep_window_uses_full_history(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        session_id = _create_test_session(database, "s_message_summary_keep_window")

        rows = []
        for turn_id in range(1, 5):
            rows.append(
                messages.append(
                    session_id,
                    models.MESSAGE_ROLE_USER,
                    f"u{turn_id}",
                    turn_id=turn_id,
                    seq_in_turn=1,
                )
            )
            rows.append(
                messages.append(
                    session_id,
                    models.MESSAGE_ROLE_ASSISTANT,
                    f"a{turn_id}",
                    turn_id=turn_id,
                    seq_in_turn=2,
                )
            )

        assert messages.mark_summary_processed(session_id, [row.id for row in rows], batch_id=1) == len(rows)

        edited_old = messages.update(rows[0].id, content="u1 edited")
        assert edited_old is not None
        assert [
            [row.content for row in group]
            for group in messages.list_summary_candidate_turn_groups(session_id, keep_recent_turns=2)
        ] == [["u1 edited"]]

        assert messages.mark_summary_processed(session_id, [edited_old.id], batch_id=2) == 1
        edited_recent = messages.update(rows[-2].id, content="u4 edited")
        assert edited_recent is not None
        assert messages.list_summary_candidate_turn_groups(session_id, keep_recent_turns=2) == []
    finally:
        database.close()


def test_message_service_replace_preserves_processing_flags_by_uid(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        session_id = _create_test_session(database, "s_message_replace_flags")

        first = messages.append(session_id, models.MESSAGE_ROLE_USER, "u1", turn_id=1, seq_in_turn=1)
        second = messages.append(session_id, models.MESSAGE_ROLE_ASSISTANT, "a1", turn_id=1, seq_in_turn=2)
        assert messages.mark_summary_processed(session_id, [first.id], batch_id=3) == 1
        assert messages.mark_story_memory_processed(session_id, [second.id]) == 1

        replacement = messages.replace(
            session_id,
            [row.to_message_dict() for row in messages.list(session_id)],
        )

        assert [row.content for row in replacement] == ["u1", "a1"]
        assert replacement[0].summary_processed
        assert replacement[0].summary_batch_id == 3
        assert not replacement[0].story_memory_processed
        assert not replacement[1].summary_processed
        assert replacement[1].story_memory_processed
    finally:
        database.close()


def test_message_service_truncate_from_turn_keeps_backup_append_only(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        backup = BackupService(database)
        session_id = _create_test_session(database, "s_message_truncate_from_turn")

        for turn_id, role, content, seq in [
            (1, models.MESSAGE_ROLE_USER, "u1", 1),
            (1, models.MESSAGE_ROLE_ASSISTANT, "a1", 2),
            (2, models.MESSAGE_ROLE_USER, "u2", 1),
            (2, models.MESSAGE_ROLE_ASSISTANT, "a2", 2),
            (3, models.MESSAGE_ROLE_USER, "u3", 1),
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

        main = messages.append(session_id, models.MESSAGE_ROLE_USER, "main", turn_id=1, seq_in_turn=1)
        cold = backup.messages.append_mapping(
            session_id,
            {
                "role": models.MESSAGE_ROLE_USER,
                "content": "main",
                "turn_id": main.turn_id,
                "seq_in_turn": main.seq_in_turn,
            },
        )
        backup.messages.append(session_id, models.MESSAGE_ROLE_ASSISTANT, "cold-only", turn_id=1, seq_in_turn=2)

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
