from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from rpg_data import db
from rpg_data.migrations.runner import MigrationHistoryError, run_migrations


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def test_run_migrations_creates_consolidated_final_schema() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)
        tables = _table_names(conn)
        assert {
            "rpg_schema_migrations",
            "rpg_workspaces",
            "rpg_stories",
            "rpg_story_openings",
            "rpg_sessions",
            "rpg_session_profiles",
            "rpg_session_messages",
            "rpg_session_backup_messages",
            "rpg_story_characters",
            "rpg_story_character_details",
            "rpg_story_lorebook_entries",
            "rpg_story_status_tables",
            "rpg_story_pack_bindings",
            "rpg_story_pack_operations",
            "rpg_session_status_tables",
            "rpg_rp_module_catalog",
            "rpg_story_rp_modules",
            "rpg_session_rp_module_overrides",
            "rpg_session_narrative_outcomes",
            "rpg_story_plot_event_pools",
            "rpg_story_plot_events",
            "rpg_story_plot_outlines",
            "rpg_story_plot_outline_nodes",
            "rpg_session_plot_schedule_decisions",
            "rpg_session_story_memories",
            "rpg_session_story_memory_evidence",
            "rpg_session_dream_proposals",
            "rpg_session_persistent_memories",
            "rpg_media_blobs",
            "rpg_media_assets",
            "rpg_media_jobs",
            "rpg_tts_blobs",
            "rpg_tts_cache_entries",
            "rpg_tts_jobs",
        }.issubset(tables)
        assert {
            "rpg_characters",
            "rpg_character_details",
            "rpg_lorebook_entries",
            "rpg_status_table_templates",
        }.isdisjoint(tables)
        assert "rpg_session_status_deferred_progress" not in tables

        assert "first_message" not in _columns(conn, "rpg_stories")
        assert {"story_prompt", "main_llm_provider_key"}.issubset(
            _columns(conn, "rpg_stories")
        )
        assert {
            "workspace_id",
            "story_id",
            "name",
            "description",
            "sort_order",
        }.issubset(_columns(conn, "rpg_story_characters"))
        assert "character_id" not in _columns(conn, "rpg_story_characters")
        assert {
            "workspace_id",
            "story_id",
            "story_character_id",
            "name",
            "status_kind",
            "document_json",
        }.issubset(_columns(conn, "rpg_story_status_tables"))
        assert {
            "source_story_status_table_id",
            "origin",
            "status_kind",
            "document_json",
        }.issubset(_columns(conn, "rpg_session_status_tables"))
        assert {
            "source_table_id",
            "story_character_mount_id",
            "mount_origin",
        }.isdisjoint(_columns(conn, "rpg_session_status_tables"))
        assert "deadline_time_json" in _columns(conn, "rpg_story_plot_events")
        assert {
            "resource_kind",
            "source_id",
            "resource_id",
            "source_digest",
            "resource_version",
        }.issubset(_columns(conn, "rpg_story_pack_bindings"))
        assert {
            "operation_kind",
            "status",
            "pack_digest",
            "pack_json",
            "plan_json",
            "result_json",
        }.issubset(_columns(conn, "rpg_story_pack_operations"))
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_run_migrations_is_idempotent_and_uses_only_three_files() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)
        run_migrations(conn)
        rows = conn.execute(
            "SELECT version, name FROM rpg_schema_migrations ORDER BY version"
        ).fetchall()
        assert [(row["version"], row["name"]) for row in rows] == [
            ("0001", "0001_initial.sql"),
            ("0002", "0002_demo.sql"),
            ("0003", "0003_pagination_demo.sql"),
        ]
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            "INSERT INTO rpg_schema_migrations (version, name, checksum) "
            "VALUES ('0020', '0020_plot_event_deadline.sql', 'legacy')",
            "unsupported pre-hard-cut migration versions",
        ),
        (
            "UPDATE rpg_schema_migrations SET name = 'legacy.sql' "
            "WHERE version = '0001'",
            "migration name mismatch",
        ),
        (
            "UPDATE rpg_schema_migrations SET checksum = 'legacy' "
            "WHERE version = '0001'",
            "migration checksum mismatch",
        ),
    ],
)
def test_migration_ledger_mismatch_fails_fast(mutation: str, message: str) -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)
        conn.execute(mutation)
        conn.commit()
        with pytest.raises(MigrationHistoryError, match=message):
            run_migrations(conn)
    finally:
        conn.close()


def test_consolidated_schema_keeps_message_and_resource_integrity() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO rpg_session_messages "
                "(session_id, role, content, mode, turn_id, seq_in_turn) "
                "VALUES ('s_forest001', 'user', 'bad', 'chat', 999, 1)"
            )
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO rpg_story_lorebook_entries "
                "(workspace_id, story_id, name) VALUES ('missing', 1, 'bad')"
            )
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO rpg_session_status_tables "
                "(session_id, workspace_id, story_id, origin, name, document_json) "
                "VALUES ('s_forest001', 'demo_workspace', 1, 'template_copy', 'bad', '{}')"
            )
        conn.rollback()

        forest_story_id = conn.execute(
            "SELECT id FROM rpg_stories WHERE title = '北境森林 Demo'"
        ).fetchone()["id"]
        academy_story_id = conn.execute(
            "SELECT id FROM rpg_stories WHERE title = '奥术学院 Demo'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO rpg_story_characters "
            "(workspace_id, story_id, name) VALUES ('demo_workspace', ?, '独立角色')",
            (forest_story_id,),
        )
        conn.execute(
            "INSERT INTO rpg_story_characters "
            "(workspace_id, story_id, name) VALUES ('demo_workspace', ?, '独立角色')",
            (academy_story_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO rpg_story_characters "
                "(workspace_id, story_id, name) VALUES ('demo_workspace', ?, '独立角色')",
                (forest_story_id,),
            )
    finally:
        conn.close()


def test_demo_data_uses_story_owned_resources_and_complete_defaults() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_stories "
            "WHERE workspace_id = 'demo_workspace'"
        ).fetchone()["count"] == 3
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_openings "
            "WHERE workspace_id = 'demo_workspace'"
        ).fetchone()["count"] == 3
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_characters "
            "WHERE workspace_id = 'demo_workspace'"
        ).fetchone()["count"] == 7
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_character_details"
        ).fetchone()["count"] == 6
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_lorebook_entries "
            "WHERE workspace_id = 'demo_workspace'"
        ).fetchone()["count"] == 4
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_status_tables "
            "WHERE workspace_id = 'demo_workspace'"
        ).fetchone()["count"] == 8
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_session_status_tables "
            "WHERE workspace_id = 'demo_workspace'"
        ).fetchone()["count"] == 8
        status_documents = [
            json.loads(str(row["document_json"]))
            for row in conn.execute(
                "SELECT document_json FROM rpg_story_status_tables"
            )
        ]
        assert status_documents
        assert all(document["schemaVersion"] == 2 for document in status_documents)
        assert all(
            "updateFrequency" not in row
            and "deferredIntervalTurns" not in row
            for document in status_documents
            for row in document["rows"]
        )

        catalog = {
            row["module_name"]
            for row in conn.execute("SELECT module_name FROM rpg_rp_module_catalog")
        }
        assert catalog == {
            "message_mode",
            "narrative_outcome",
            "plot_scheduler",
            "dice",
        }
        expected_modules_by_story = {
            1: catalog,
            2: catalog,
            3: catalog,
        }
        for story_id, expected_modules in expected_modules_by_story.items():
            mounted = {
                row["module_name"]
                for row in conn.execute(
                    "SELECT module_name FROM rpg_story_rp_modules WHERE story_id = ?",
                    (story_id,),
                )
            }
            assert mounted == expected_modules
            assert conn.execute(
                "SELECT COUNT(*) AS count FROM rpg_story_narrative_styles "
                "WHERE story_id = ?",
                (story_id,),
            ).fetchone()["count"] == 3

        snapshots = [
            str(row["player_character_snapshot_json"])
            for row in conn.execute(
                "SELECT player_character_snapshot_json FROM rpg_session_profiles"
            )
        ]
        assert snapshots
        assert all('"mountId"' not in snapshot for snapshot in snapshots)
        forest_bob = conn.execute(
            "SELECT characters.id FROM rpg_story_characters AS characters "
            "JOIN rpg_stories AS stories ON stories.id = characters.story_id "
            "WHERE stories.title = '北境森林 Demo' AND characters.name = 'Bob'"
        ).fetchone()["id"]
        pagination_bob = conn.execute(
            "SELECT characters.id FROM rpg_story_characters AS characters "
            "JOIN rpg_stories AS stories ON stories.id = characters.story_id "
            "WHERE stories.title = '分页压力测试 Demo' AND characters.name = 'Bob'"
        ).fetchone()["id"]
        assert forest_bob != pagination_bob
        assert conn.execute(
            "SELECT id FROM rpg_workspaces WHERE id = 'default'"
        ).fetchone() is None
    finally:
        conn.close()


def test_primary_demo_sessions_include_rich_runtime_fixtures() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        history_counts = {
            row["session_id"]: (row["turn_count"], row["message_count"])
            for row in conn.execute(
                "SELECT session_id, COUNT(DISTINCT turn_id) AS turn_count, "
                "COUNT(*) AS message_count "
                "FROM rpg_session_messages "
                "WHERE session_id IN ('s_forest001', 's_academy01') "
                "GROUP BY session_id"
            )
        }
        assert history_counts == {
            "s_forest001": (14, 28),
            "s_academy01": (12, 24),
        }
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_session_messages "
            "WHERE session_id IN ('s_forest001', 's_academy01') "
            "AND role = 'assistant' AND content LIKE '%<rp-narration>%'"
        ).fetchone()["count"] == 12

        summary_ranges = [
            (
                row["session_id"],
                row["summary_batch_id"],
                row["turn_start"],
                row["turn_end"],
                row["message_count"],
            )
            for row in conn.execute(
                "SELECT session_id, summary_batch_id, "
                "MIN(turn_id) AS turn_start, MAX(turn_id) AS turn_end, "
                "COUNT(*) AS message_count "
                "FROM rpg_session_messages "
                "WHERE summary_processed = 1 "
                "GROUP BY session_id, summary_batch_id "
                "ORDER BY session_id, summary_batch_id"
            )
        ]
        assert summary_ranges == [
            ("s_academy01", 1, 1, 6, 12),
            ("s_academy01", 2, 7, 10, 8),
            ("s_forest001", 1, 1, 6, 12),
            ("s_forest001", 2, 7, 12, 12),
        ]

        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_plot_event_pools"
        ).fetchone()["count"] == 4
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_plot_events"
        ).fetchone()["count"] == 12
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_plot_outlines"
        ).fetchone()["count"] == 2
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_plot_outline_nodes"
        ).fetchone()["count"] == 8
        decisions = list(
            conn.execute(
                "SELECT decision_status, event_snapshot_json "
                "FROM rpg_session_plot_schedule_decisions"
            )
        )
        assert len(decisions) == 8
        assert all(row["decision_status"] == "triggered" for row in decisions)
        snapshots = [
            json.loads(str(row["event_snapshot_json"]))
            for row in decisions
        ]
        assert all(
            snapshot.get("eventTitle") and snapshot.get("directive")
            for snapshot in snapshots
        )

        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_session_story_memories"
        ).fetchone()["count"] == 12
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_session_story_memory_evidence"
        ).fetchone()["count"] == 13
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_session_persistent_memories "
            "WHERE lifecycle = 'active'"
        ).fetchone()["count"] == 6
        assert conn.execute(
            "SELECT COUNT(*) AS count "
            "FROM rpg_session_persistent_memory_revisions"
        ).fetchone()["count"] == 6
        assert conn.execute(
            "SELECT COUNT(*) AS count "
            "FROM rpg_session_persistent_memory_evidence"
        ).fetchone()["count"] == 6

        evidence_queries = (
            (
                "rpg_session_story_memory_evidence",
                "JOIN rpg_session_story_memories AS owner "
                "ON owner.id = evidence.story_memory_id",
            ),
            (
                "rpg_session_persistent_memory_evidence",
                "JOIN rpg_session_persistent_memory_revisions AS owner "
                "ON owner.id = evidence.revision_id",
            ),
        )
        for table, owner_join in evidence_queries:
            rows = conn.execute(
                "SELECT evidence.content_hash, messages.content, "
                "evidence.turn_id, evidence.message_version, "
                "messages.turn_id AS message_turn_id, "
                "messages.version AS current_message_version "
                f"FROM {table} AS evidence "
                f"{owner_join} "
                "JOIN rpg_session_messages AS messages "
                "ON messages.id = evidence.message_id"
            )
            for row in rows:
                assert row["content_hash"] == hashlib.sha256(
                    str(row["content"]).encode("utf-8")
                ).hexdigest()
                assert row["turn_id"] == row["message_turn_id"]
                assert row["message_version"] == row["current_message_version"]

        bound_story_tables = list(
            conn.execute(
                "SELECT id FROM rpg_story_status_tables "
                "WHERE story_character_id IS NOT NULL"
            )
        )
        assert len(bound_story_tables) == 2
        copied_metadata = [
            json.loads(str(row["metadata_json"]))
            for row in conn.execute(
                "SELECT metadata_json FROM rpg_session_status_tables "
                "WHERE source_story_status_table_id IN "
                "(SELECT id FROM rpg_story_status_tables "
                "WHERE story_character_id IS NOT NULL)"
            )
        ]
        assert len(copied_metadata) == 2
        assert all(
            item["storyStatusSource"]["characterId"] is not None
            and item["storyStatusSource"]["characterName"]
            for item in copied_metadata
        )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_pagination_demo_keeps_long_history_and_story_owned_player() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)
        story = conn.execute(
            "SELECT id, story_prompt, metadata_json FROM rpg_stories "
            "WHERE title = '分页压力测试 Demo'"
        ).fetchone()
        assert story is not None
        opening = conn.execute(
            "SELECT message FROM rpg_story_openings WHERE story_id = ?",
            (story["id"],),
        ).fetchone()
        profile = conn.execute(
            "SELECT player_character_id, player_character_snapshot_json "
            "FROM rpg_session_profiles WHERE session_id = 's_pagination001'"
        ).fetchone()
        assert "分页" in opening["message"]
        assert profile["player_character_id"] is not None
        assert f'"storyId":{story["id"]}' in profile["player_character_snapshot_json"]
        assert '"mountId"' not in profile["player_character_snapshot_json"]
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_session_messages "
            "WHERE session_id = 's_pagination001'"
        ).fetchone()["count"] == 320
        assert conn.execute(
            "SELECT COUNT(DISTINCT turn_id) AS count FROM rpg_session_messages "
            "WHERE session_id = 's_pagination001'"
        ).fetchone()["count"] == 160
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_session_backup_messages "
            "WHERE session_id = 's_pagination001'"
        ).fetchone()["count"] == 320
    finally:
        conn.close()
