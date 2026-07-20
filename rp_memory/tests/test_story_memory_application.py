from __future__ import annotations

from pathlib import Path

import pytest
from peewee import SqliteDatabase

from commons.errors import InvalidTurnMetadataError
from rpg_data import db, models
from rpg_data.migrations.runner import run_migrations
from rpg_data.services.message import MessageService
from rpg_data.services.story_memory import StoryMemoryDataService
from rp_memory.story_memory_service import StoryMemoryApplicationService


def _migrated_database(tmp_path: Path) -> SqliteDatabase:
    db_path = tmp_path / "story-memory.sqlite3"
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


def _story_memory(database: SqliteDatabase) -> StoryMemoryApplicationService:
    return StoryMemoryApplicationService(StoryMemoryDataService(database))


def test_story_memory_service_crud(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        story_memory = _story_memory(database)

        first = story_memory.add_detail("s_forest001", "remember this", turn_id=2)
        second = story_memory.add_detail(
            "s_forest001",
            "dream this",
            turn_id=3,
            dream_processed=True,
            memory_kind="clue",
            epistemic_status="reported",
            salience=0.8,
            source_turn_start=2,
            source_turn_end=3,
            metadata_json='{"kind":"test"}',
        )

        assert [row.text for row in story_memory.list("s_forest001")] == [
            "remember this",
            "dream this",
        ]
        assert [
            row.id
            for row in story_memory.list("s_forest001", dream_processed=True)
        ] == [second.id]
        context_by_id = {
            item.id: item.to_context_dict()
            for item in story_memory.get_context_items("s_forest001")
        }
        assert context_by_id[first.id]["turn_id"] == 2
        assert context_by_id[second.id]["metadata"] == {"kind": "test"}
        assert story_memory.get(second.id).memory_kind == "clue"
        assert story_memory.get(second.id).epistemic_status == "reported"
        assert story_memory.get(second.id).source_turn_start == 2

        duplicate = story_memory.add_detail(
            "s_forest001",
            "dream this",
            turn_id=4,
            memory_kind="clue",
            salience=0.9,
        )
        assert duplicate.id == second.id
        assert duplicate.created_at == second.created_at
        assert duplicate.salience == 0.9
        assert duplicate.source_turn_end == 4
        assert duplicate.version == second.version + 1
        duplicate_context = next(
            item
            for item in story_memory.get_context_items("s_forest001")
            if item.id == duplicate.id
        )
        assert duplicate_context.to_context_dict()["metadata"] == {"kind": "test"}

        assert len(story_memory.list("s_forest001")) == 2

        assert story_memory.set_dream_processed(
            [first.id],
            dream_processed=True,
        ) == 1
        assert {
            row.id
            for row in story_memory.list("s_forest001", dream_processed=True)
        } == {first.id, second.id}

        replacement = story_memory.set_details(
            "s_forest001",
            [
                {
                    "text": "replacement",
                    "turn_id": 4,
                    "metadata": {"kind": "unit"},
                },
            ],
        )
        assert [row.text for row in replacement] == ["replacement"]
        assert story_memory.get_context_items("s_forest001")[0].to_context_dict()[
            "metadata"
        ] == {"kind": "unit"}

        with pytest.raises(InvalidTurnMetadataError):
            story_memory.add_detail("s_forest001", "missing turn", turn_id=0)
        with pytest.raises(InvalidTurnMetadataError):
            story_memory.set_details("s_forest001", [{"text": "invalid"}])
        assert [row.text for row in story_memory.list("s_forest001")] == [
            "replacement"
        ]
    finally:
        database.close()


def test_story_memory_service_lists_filtered_pages_and_session_stats(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)
    try:
        story_memory = _story_memory(database)
        session_id = _create_test_session(database, "s_story_page")
        first = story_memory.add_detail(
            session_id,
            "第一条事件",
            turn_id=1,
            memory_kind="event",
        )
        second = story_memory.add_detail(
            session_id,
            "关键线索",
            turn_id=2,
            memory_kind="clue",
            dream_processed=True,
        )
        third = story_memory.add_detail(
            session_id,
            "关系变化",
            turn_id=3,
            memory_kind="relationship",
        )

        page = story_memory.list_page(session_id, page=1, page_size=2)
        assert [item.id for item in page.items] == [third.id, second.id]
        assert page.total == 3
        assert page.page == 1
        assert page.page_size == 2
        assert page.stats.total_facts == 3
        assert page.stats.dream_processed_facts == 1
        assert page.stats.pending_dream_facts == 2
        assert page.stats.latest_updated_at

        filtered = story_memory.list_page(
            session_id,
            memory_kind="event",
            dream_processed=False,
        )
        assert [item.id for item in filtered.items] == [first.id]
        assert filtered.total == 1
        assert filtered.stats.total_facts == 3

        with pytest.raises(ValueError, match="memory_kind"):
            story_memory.list_page(session_id, memory_kind="invalid")
        with pytest.raises(ValueError, match="page_size"):
            story_memory.list_page(session_id, page_size=101)
    finally:
        database.close()


def test_story_memory_batch_and_progress_commit_atomically(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        story_memory = _story_memory(database)
        session_id = _create_test_session(database, "s_story_atomic")
        rows = [
            messages.append(
                session_id,
                models.MESSAGE_ROLE_USER,
                "u",
                turn_id=1,
                seq_in_turn=1,
            ),
            messages.append(
                session_id,
                models.MESSAGE_ROLE_ASSISTANT,
                "a",
                turn_id=1,
                seq_in_turn=2,
            ),
        ]

        saved = story_memory.add_details_and_mark_processed(
            session_id,
            [
                {
                    "text": "角色听说北门已经关闭。",
                    "turn_id": 1,
                    "memory_kind": "world_fact",
                    "epistemic_status": "reported",
                    "salience": 0.7,
                    "source_turn_start": 1,
                    "source_turn_end": 1,
                    "evidence_message_ids": [rows[1].id],
                    "metadata": {"location": "北门"},
                }
            ],
            message_ids=[row.id for row in rows],
        )
        assert len(saved) == 1
        assert [item.message_id for item in saved[0].evidence] == [rows[1].id]
        assert saved[0].evidence[0].message_version == 1
        assert len(saved[0].evidence[0].content_hash) == 64
        assert all(messages.get(row.id).story_memory_processed for row in rows)

        with pytest.raises(ValueError, match="belong to the session"):
            story_memory.add_details_and_mark_processed(
                session_id,
                [
                    {
                        "text": "不应写入",
                        "turn_id": 2,
                        "evidence_message_ids": [999999],
                    }
                ],
                message_ids=[999999],
            )
        assert [row.text for row in story_memory.list(session_id)] == [
            "角色听说北门已经关闭。"
        ]
    finally:
        database.close()


def test_story_memory_evidence_preserves_large_backlog(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        story_memory = _story_memory(database)
        session_id = _create_test_session(database, "s_story_large_backlog")
        rows = []
        for index in range(65):
            turn_id = index // 2 + 1
            seq_in_turn = index % 2 + 1
            role = (
                models.MESSAGE_ROLE_USER
                if seq_in_turn == 1
                else models.MESSAGE_ROLE_ASSISTANT
            )
            rows.append(
                messages.append(
                    session_id,
                    role,
                    f"message-{index}",
                    turn_id=turn_id,
                    seq_in_turn=seq_in_turn,
                )
            )

        saved = story_memory.add_details_and_mark_processed(
            session_id,
            [
                {
                    "text": "长时间积压的剧情已完成归纳。",
                    "turn_id": 33,
                    "source_turn_start": 1,
                    "source_turn_end": 33,
                    "evidence_message_ids": [row.id for row in rows],
                }
            ],
            message_ids=[row.id for row in rows],
        )

        assert len(saved[0].evidence) == 65
        assert [item.message_id for item in saved[0].evidence] == [
            row.id for row in rows
        ]
        assert all(messages.get(row.id).story_memory_processed for row in rows)
    finally:
        database.close()


def test_story_memory_exact_upsert_replaces_evidence_instead_of_union(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        story_memory = _story_memory(database)
        session_id = _create_test_session(database, "s_story_evidence_replace")
        first_source = messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "守卫第一次交出铜钥匙。",
            turn_id=1,
            seq_in_turn=1,
        )
        second_source = messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "守卫再次确认铜钥匙已交给阿澈。",
            turn_id=2,
            seq_in_turn=1,
        )
        detail = {
            "text": "守卫把铜钥匙交给阿澈。",
            "turn_id": 1,
            "memory_kind": "clue",
            "evidence_message_ids": [first_source.id],
        }
        first = story_memory.add_details_and_mark_processed(
            session_id,
            (detail,),
            message_ids=(first_source.id,),
        )[0]
        detail["turn_id"] = 2
        detail["evidence_message_ids"] = [second_source.id]
        refreshed = story_memory.add_details_and_mark_processed(
            session_id,
            (detail,),
            message_ids=(second_source.id,),
        )[0]

        assert refreshed.id == first.id
        assert refreshed.version == first.version + 1
        assert [item.message_id for item in refreshed.evidence] == [second_source.id]
        assert refreshed.source_turn_start == refreshed.source_turn_end == 2
    finally:
        database.close()


def test_story_memory_fact_evidence_and_progress_roll_back_together(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)
    try:
        messages = MessageService(database)
        story_memory = _story_memory(database)
        session_id = _create_test_session(database, "s_story_atomic_rollback")
        batch_source = messages.append(
            session_id,
            models.MESSAGE_ROLE_USER,
            "当前批次",
            turn_id=1,
            seq_in_turn=1,
        )
        outside_source = messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            "不属于当前批次",
            turn_id=2,
            seq_in_turn=1,
        )

        with pytest.raises(ValueError, match="current source batch"):
            story_memory.add_details_and_mark_processed(
                session_id,
                (
                    {
                        "text": "本应随事务回滚。",
                        "turn_id": 1,
                        "evidence_message_ids": [batch_source.id],
                    },
                    {
                        "text": "引用批次外来源。",
                        "turn_id": 2,
                        "evidence_message_ids": [outside_source.id],
                    },
                ),
                message_ids=(batch_source.id,),
            )

        assert story_memory.list(session_id) == []
        assert messages.get(batch_source.id).story_memory_processed is False
    finally:
        database.close()
