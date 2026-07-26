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


def test_message_history_search_groups_ranks_and_scopes_turns(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        session_id = _create_test_session(database, "s_history_search")
        other_session_id = _create_test_session(database, "s_history_search_other")

        messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "艾琳独自等待。",
            mode=models.TURN_MODE_OOC,
            turn_id=10,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "钟楼敲响，约定会合。",
            mode=models.TURN_MODE_OOC,
            turn_id=10,
            seq_in_turn=2,
        )
        turn_20_user = messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "艾琳将在钟楼等待。",
            mode=models.TURN_MODE_GM,
            turn_id=20,
            seq_in_turn=1,
        )
        turn_20_assistant = messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "他们随后会合。",
            mode=models.TURN_MODE_GM,
            turn_id=20,
            seq_in_turn=2,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "艾琳",
            mode=models.TURN_MODE_IC,
            turn_id=30,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_SYSTEM,
            "艾琳 钟楼 会合",
            turn_id=40,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_TOOL,
            "艾琳 钟楼 会合",
            turn_id=40,
            seq_in_turn=2,
        )
        messages.append(
            other_session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "艾琳 钟楼 会合",
            turn_id=99,
            seq_in_turn=1,
        )

        assert messages.mark_summary_processed(
            session_id,
            [turn_20_user.id, turn_20_assistant.id],
            batch_id=3,
        ) == 2
        assert messages.mark_story_memory_processed(
            session_id,
            [turn_20_user.id, turn_20_assistant.id],
        ) == 2

        hits = messages.search_history_turns(
            session_id,
            (" 艾琳 ", "钟楼", "会合", "艾琳", ""),
            limit=9,
        )

        assert [hit.turn_id for hit in hits] == [20, 10, 30]
        assert hits[0] == models.SessionHistorySearchHit(
            turn_id=20,
            message_id=turn_20_user.id,
            seq_in_turn=1,
            role=models.MESSAGE_ROLE_USER,
            mode=models.TURN_MODE_GM,
            content="艾琳将在钟楼等待。",
            matched_terms=("艾琳", "钟楼", "会合"),
        )
        assert hits[1].matched_terms == ("艾琳", "钟楼", "会合")
        assert hits[1].content == "钟楼敲响，约定会合。"
        assert [hit.turn_id for hit in messages.search_history_turns(
            session_id,
            ("艾琳", "钟楼", "会合"),
            limit=2,
        )] == [20, 10]
    finally:
        database.close()


def test_message_history_search_uses_literal_ascii_folded_terms(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        session_id = _create_test_session(database, "s_history_search_literals")

        special = messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "进度 100%_CLOCK；代号 ÉLAN。",
            turn_id=1,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "只有普通的 CLOCK 文本",
            turn_id=2,
            seq_in_turn=1,
        )

        literal_hits = messages.search_history_turns(
            session_id,
            ("clock", "%", "_"),
            limit=9,
        )
        assert [hit.turn_id for hit in literal_hits] == [1, 2]
        assert literal_hits[0].message_id == special.id
        assert literal_hits[0].matched_terms == ("clock", "%", "_")
        assert literal_hits[1].matched_terms == ("clock",)

        ascii_duplicate_hits = messages.search_history_turns(
            session_id,
            ("CLOCK", "clock"),
            limit=9,
        )
        assert all(hit.matched_terms == ("CLOCK",) for hit in ascii_duplicate_hits)

        unicode_hits = messages.search_history_turns(
            session_id,
            ("ÉLAN", "élan"),
            limit=9,
        )
        assert [hit.turn_id for hit in unicode_hits] == [1]
        assert unicode_hits[0].matched_terms == ("ÉLAN",)
    finally:
        database.close()


def test_message_history_search_uses_term_length_then_message_sequence_ties(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        session_id = _create_test_session(database, "s_history_search_ties")
        newer_short = messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "x appears in the newer turn",
            turn_id=20,
            seq_in_turn=1,
        )
        older_long_first = messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "longterm appears first",
            turn_id=10,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "longterm appears again",
            turn_id=10,
            seq_in_turn=2,
        )

        hits = messages.search_history_turns(
            session_id,
            ("x", "longterm"),
            limit=9,
        )

        assert [hit.turn_id for hit in hits] == [10, 20]
        assert hits[0].message_id == older_long_first.id
        assert hits[0].matched_terms == ("longterm",)
        assert hits[1].message_id == newer_short.id
        assert hits[1].matched_terms == ("x",)
    finally:
        database.close()


def test_message_history_search_bounds_content_fetch_to_ranked_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        session_id = _create_test_session(database, "s_history_search_bounded")
        for turn_id in range(1, 31):
            messages.append(
                session_id,
                models.MESSAGE_ROLE_USER,
                f"common marker from turn {turn_id}",
                turn_id=turn_id,
                seq_in_turn=1,
            )

        executed_selects: list[tuple[str, tuple[object, ...], tuple[str, ...]]] = []
        original_execute_sql = database.execute_sql

        def capture_execute_sql(sql: str, params=None):
            cursor = original_execute_sql(sql, params)
            if (
                sql.lstrip().upper().startswith("SELECT")
                and 'FROM "rpg_session_messages"' in sql
            ):
                columns = tuple(
                    str(description[0])
                    for description in (cursor.description or ())
                )
                executed_selects.append((sql, tuple(params or ()), columns))
            return cursor

        monkeypatch.setattr(database, "execute_sql", capture_execute_sql)

        hits = messages.search_history_turns(
            session_id,
            ("common",),
            limit=2,
        )

        assert [hit.turn_id for hit in hits] == [30, 29]
        assert len(executed_selects) == 2
        candidate_sql, candidate_params, candidate_columns = executed_selects[0]
        content_sql, _, content_columns = executed_selects[1]
        assert candidate_columns == ("turn_id", "term_match_0")
        assert " LIMIT ?" in candidate_sql.upper()
        assert candidate_params[-1] == 2
        assert "common" not in candidate_sql
        assert "common" in candidate_params
        assert content_columns == (
            "id",
            "turn_id",
            "seq_in_turn",
            "role",
            "mode",
            "content",
        )
        assert " IN (?, ?)" in content_sql.upper()
    finally:
        database.close()


def test_message_history_search_validates_query_shape(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        session_id = _create_test_session(database, "s_history_search_validation")

        for terms in (
            (),
            (" ",),
            "term",
            ("x" * 65,),
            tuple(str(index) for index in range(9)),
            ("valid", 1),
        ):
            with pytest.raises(ValueError):
                messages.search_history_turns(session_id, terms, limit=1)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="limit must be positive"):
            messages.search_history_turns(session_id, ("term",), limit=0)
    finally:
        database.close()


def test_message_history_turn_window_uses_actual_turns_and_boundaries(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        session_id = _create_test_session(database, "s_history_window")
        other_session_id = _create_test_session(database, "s_history_window_other")

        messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "turn 2",
            turn_id=2,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_SYSTEM,
            "turn 5 system",
            turn_id=5,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "turn 5 user",
            mode=models.TURN_MODE_OOC,
            turn_id=5,
            seq_in_turn=2,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "turn 5 assistant",
            mode=models.TURN_MODE_OOC,
            turn_id=5,
            seq_in_turn=3,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_SYSTEM,
            "turn 7 system only",
            turn_id=7,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_TOOL,
            "turn 7 tool only",
            turn_id=7,
            seq_in_turn=2,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "turn 9",
            turn_id=9,
            seq_in_turn=1,
        )
        messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "turn 20",
            turn_id=20,
            seq_in_turn=1,
        )
        messages.append(
            other_session_id,
            models.MESSAGE_ROLE_USER,
            "other turn 7",
            turn_id=7,
            seq_in_turn=1,
        )

        window = messages.read_history_turn_window(
            session_id,
            anchor_turn_id=5,
            before_turns=2,
            after_turns=1,
        )
        assert window is not None
        assert window.anchor_turn_id == 5
        assert window.turn_ids == (2, 5, 9)
        assert [(row.turn_id, row.seq_in_turn, row.content) for row in window.messages] == [
            (2, 1, "turn 2"),
            (5, 2, "turn 5 user"),
            (5, 3, "turn 5 assistant"),
            (9, 1, "turn 9"),
        ]
        assert window.has_before is False
        assert window.has_after is True

        later_window = messages.read_history_turn_window(
            session_id,
            anchor_turn_id=9,
            before_turns=1,
            after_turns=2,
        )
        assert later_window is not None
        assert later_window.turn_ids == (5, 9, 20)
        assert later_window.has_before is True
        assert later_window.has_after is False

        anchor_only = messages.read_history_turn_window(
            session_id,
            anchor_turn_id=9,
            before_turns=0,
            after_turns=0,
        )
        assert anchor_only is not None
        assert anchor_only.turn_ids == (9,)
        assert anchor_only.has_before is True
        assert anchor_only.has_after is True

        assert messages.read_history_turn_window(
            session_id,
            anchor_turn_id=7,
            before_turns=1,
            after_turns=1,
        ) is None
    finally:
        database.close()


def test_message_history_turn_window_validates_bounds(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        session_id = _create_test_session(database, "s_history_window_validation")

        for kwargs in (
            {"anchor_turn_id": 0, "before_turns": 0, "after_turns": 0},
            {"anchor_turn_id": 1, "before_turns": -1, "after_turns": 0},
            {"anchor_turn_id": 1, "before_turns": 3, "after_turns": 0},
            {"anchor_turn_id": 1, "before_turns": 0, "after_turns": -1},
            {"anchor_turn_id": 1, "before_turns": 0, "after_turns": 3},
        ):
            with pytest.raises(ValueError):
                messages.read_history_turn_window(session_id, **kwargs)
    finally:
        database.close()


def test_message_history_queries_follow_mutable_main_history_only(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageDataService(database)
        backup = BackupService(database)
        session_id = _create_test_session(database, "s_history_mutations")

        main = messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "旧线索",
            turn_id=1,
            seq_in_turn=1,
        )
        backup.messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "冷备秘密",
            turn_id=1,
            seq_in_turn=1,
        )
        assert messages.mark_summary_processed(
            session_id,
            [main.id],
            batch_id=1,
        ) == 1
        assert messages.mark_story_memory_processed(session_id, [main.id]) == 1
        assert [hit.turn_id for hit in messages.search_history_turns(
            session_id,
            ("旧线索",),
            limit=9,
        )] == [1]
        assert messages.search_history_turns(
            session_id,
            ("冷备秘密",),
            limit=9,
        ) == []
        initial_window = messages.read_history_turn_window(
            session_id,
            anchor_turn_id=1,
            before_turns=0,
            after_turns=0,
        )
        assert initial_window is not None
        assert [row.content for row in initial_window.messages] == ["旧线索"]

        updated = messages.update(main.id, content="新线索")
        assert updated is not None
        assert messages.search_history_turns(session_id, ("旧线索",), limit=9) == []
        assert [hit.turn_id for hit in messages.search_history_turns(
            session_id,
            ("新线索",),
            limit=9,
        )] == [1]
        updated_window = messages.read_history_turn_window(
            session_id,
            anchor_turn_id=1,
            before_turns=0,
            after_turns=0,
        )
        assert updated_window is not None
        assert [row.content for row in updated_window.messages] == ["新线索"]

        assert messages.delete(main.id)
        assert messages.search_history_turns(session_id, ("新线索",), limit=9) == []
        assert messages.read_history_turn_window(
            session_id,
            anchor_turn_id=1,
            before_turns=0,
            after_turns=0,
        ) is None
        messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "截断目标",
            turn_id=2,
            seq_in_turn=1,
        )
        backup.messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "截断目标",
            turn_id=2,
            seq_in_turn=1,
        )
        assert messages.truncate_from_turn(session_id, 2) == 1
        assert messages.search_history_turns(
            session_id,
            ("截断目标",),
            limit=9,
        ) == []
        assert messages.read_history_turn_window(
            session_id,
            anchor_turn_id=2,
            before_turns=0,
            after_turns=0,
        ) is None

        messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "清空目标",
            turn_id=3,
            seq_in_turn=1,
        )
        assert messages.clear(session_id) == 1
        assert messages.search_history_turns(
            session_id,
            ("清空目标",),
            limit=9,
        ) == []
        assert messages.read_history_turn_window(
            session_id,
            anchor_turn_id=3,
            before_turns=0,
            after_turns=0,
        ) is None
        assert backup.messages.count(session_id) == 2
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
