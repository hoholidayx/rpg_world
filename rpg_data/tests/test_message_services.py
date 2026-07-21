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
from rpg_data.services.message import MessageDataService


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
        messages = MessageDataService(database)
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
        assert updated.version == second.version + 1

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


def test_message_mode_is_persisted_in_main_backup_and_replace(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        backup = BackupService(database)
        session_id = _create_test_session(database, "s_message_modes")

        user = messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "场外问题",
            mode=models.TURN_MODE_OOC,
            turn_id=1,
            seq_in_turn=1,
        )
        backup.messages.append_mapping(session_id, user)
        assistant = messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "场外回答",
            mode=models.TURN_MODE_OOC,
            turn_id=1,
            seq_in_turn=2,
        )
        backup.messages.append_mapping(session_id, assistant)

        assert [row.mode for row in messages.list(session_id)] == ["ooc", "ooc"]
        assert [row.mode for row in backup.messages.list(session_id)] == ["ooc", "ooc"]
        assert messages.mark_summary_processed(
            session_id,
            [user.id, assistant.id],
            batch_id=None,
        ) == 2
        excluded = messages.list(session_id)
        assert all(row.summary_processed for row in excluded)
        assert all(row.summary_batch_id is None for row in excluded)
        updated = messages.update(user.id, content="编辑后的场外问题")
        assert updated is not None and updated.mode == "ooc"

        replaced = messages.replace(
            session_id,
            [row.to_message_dict() for row in messages.list(session_id)],
        )
        assert [row.mode for row in replaced] == ["ooc", "ooc"]
        with pytest.raises(ValueError, match="invalid session message mode"):
            messages.append(
                session_id,
                models.MESSAGE_ROLE_USER,
                "bad",
                mode="chat",
                turn_id=2,
                seq_in_turn=1,
            )
    finally:
        database.close()


def test_message_service_turn_window_pagination(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        session_id = _create_test_session(database, "s_message_turn_window")

        for turn_id in range(1, 6):
            messages.append(session_id, models.MESSAGE_ROLE_USER, f"u{turn_id}", turn_id=turn_id, seq_in_turn=1)
            messages.append(session_id, models.MESSAGE_ROLE_ASSISTANT, f"a{turn_id}", turn_id=turn_id, seq_in_turn=2)

        latest = messages.list_turn_window(session_id, limit=2)
        before = messages.list_turn_window(session_id, limit=2, before_turn_id=4)
        after = messages.list_turn_window(session_id, limit=2, after_turn_id=2)
        exact = messages.list_turn(session_id, 3)

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
        assert [(row.turn_id, row.content) for row in exact] == [
            (3, "u3"),
            (3, "a3"),
        ]
        assert messages.list_turn(session_id, 99) == []
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
        messages = MessageDataService(database)
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
        messages = MessageDataService(database)
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


def test_message_data_service_processing_flags(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
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
        messages.append(
            session_id,
            models.MESSAGE_ROLE_SYSTEM,
            "system",
            turn_id=4,
            seq_in_turn=1,
        )

        assert messages.count_distinct_turns(
            session_id,
            story_memory_processed=False,
        ) == 4
        assert messages.count_distinct_turns(
            session_id,
            excluded_roles=(models.MESSAGE_ROLE_SYSTEM,),
            story_memory_processed=False,
        ) == 3

        first_turn_ids = [row.id for row in rows[:2]]
        assert messages.mark_summary_processed(session_id, first_turn_ids, batch_id=7) == 2
        marked = [messages.get(row_id) for row_id in first_turn_ids]
        assert all(row is not None and row.summary_processed for row in marked)
        assert {row.summary_batch_id for row in marked if row is not None} == {7}
        assert messages.list_summary_turn_ranges(session_id) == {7: (1, 1)}
        assert messages.count_distinct_turns(
            session_id,
            excluded_roles=(models.MESSAGE_ROLE_SYSTEM,),
            summary_processed=False,
        ) == 2
        assert messages.mark_story_memory_processed(session_id, [row.id for row in rows[:4]]) == 4
        assert [
            row.content
            for row in messages.list_filtered(
                session_id,
                excluded_roles=(models.MESSAGE_ROLE_SYSTEM,),
                story_memory_processed=False,
            )
        ] == ["u3", "a3"]
        assert messages.count_distinct_turns(
            session_id,
            excluded_roles=(models.MESSAGE_ROLE_SYSTEM,),
            story_memory_processed=False,
        ) == 1

        updated = messages.update(first_turn_ids[0], content="u1 edited")
        assert updated is not None
        assert updated.content == "u1 edited"
        edited = messages.get(first_turn_ids[0])
        untouched = messages.get(first_turn_ids[1])
        assert edited is not None and edited.summary_processed
        assert edited.summary_batch_id == 7
        assert edited.story_memory_processed
        assert untouched is not None and untouched.summary_processed
        assert untouched.summary_batch_id == 7
        assert untouched.story_memory_processed
        assert messages.list_summary_turn_ranges(session_id) == {7: (1, 1)}

        assert messages.reset_processing_for_messages(
            session_id,
            [first_turn_ids[0]],
        ) == 1
        reset = messages.get(first_turn_ids[0])
        assert reset is not None and not reset.summary_processed
        assert reset.summary_batch_id is None
        assert not reset.story_memory_processed

        cold = backup.messages.list(session_id)[0]
        assert cold.summary_processed is False
        assert cold.story_memory_processed is False
    finally:
        database.close()


def test_message_service_rejects_turn_metadata_update(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
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


def test_message_service_truncate_from_turn_keeps_backup_append_only(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
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
        messages = MessageDataService(database)
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
