from __future__ import annotations

import sqlite3

import pytest

from rpg_data import db
from rpg_data.migrations import runner as migration_runner
from rpg_data.migrations.runner import run_migrations


def test_run_migrations_creates_initial_tables() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        tables = {
            row["name"]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        assert {
            "rpg_schema_migrations",
            "rpg_workspaces",
            "rpg_stories",
            "rpg_sessions",
            "rpg_session_profiles",
            "rpg_session_messages",
            "rpg_session_backup_messages",
            "rpg_session_story_memories",
            "rpg_session_dream_proposals",
            "rpg_session_dream_proposal_items",
            "rpg_session_dream_proposal_item_evidence",
            "rpg_session_persistent_memories",
            "rpg_session_persistent_memory_revisions",
            "rpg_session_persistent_memory_evidence",
            "rpg_session_dream_states",
            "rpg_session_narrative_outcomes",
            "rpg_rp_module_catalog",
            "rpg_story_rp_modules",
            "rpg_session_rp_module_overrides",
            "rpg_workspace_turn_modes",
            "rpg_narrative_styles",
            "rpg_story_narrative_styles",
            "rpg_story_quick_replies",
            "rpg_characters",
            "rpg_character_details",
            "rpg_lorebook_entries",
            "rpg_story_characters",
            "rpg_story_lorebook_entries",
            "rpg_status_table_templates",
            "rpg_story_status_tables",
            "rpg_session_status_tables",
            "rpg_media_blobs",
            "rpg_media_assets",
            "rpg_media_jobs",
            "rpg_session_media_gallery_items",
            "rpg_session_media_backgrounds",
        }.issubset(tables)

        for table in (
            "rpg_workspaces",
            "rpg_stories",
            "rpg_sessions",
            "rpg_session_profiles",
            "rpg_session_messages",
            "rpg_session_backup_messages",
            "rpg_session_story_memories",
            "rpg_session_narrative_outcomes",
            "rpg_characters",
            "rpg_character_details",
            "rpg_lorebook_entries",
            "rpg_story_characters",
            "rpg_story_lorebook_entries",
            "rpg_status_table_templates",
            "rpg_story_status_tables",
            "rpg_session_status_tables",
        ):
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert {"created_at", "updated_at", "version"}.issubset(columns)

        session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_sessions)")}
        story_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_stories)")}
        session_message_info = {
            row["name"]: row
            for row in conn.execute("PRAGMA table_info(rpg_session_messages)")
        }
        session_message_columns = set(session_message_info)
        backup_message_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_session_backup_messages)")}
        story_memory_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_session_story_memories)")}
        dream_item_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(rpg_session_dream_proposal_items)"
            )
        }
        narrative_outcome_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(rpg_session_narrative_outcomes)")
        }
        character_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_characters)")}
        character_detail_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_character_details)")}
        lorebook_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_lorebook_entries)")}
        story_character_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_story_characters)")}
        story_lorebook_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_story_lorebook_entries)")}
        status_template_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_status_table_templates)")}
        story_status_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_story_status_tables)")}
        session_status_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_session_status_tables)")}

        profile_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_session_profiles)")}

        assert "story_memory_last_turn_id" not in session_columns
        assert "last_story_turn_index" not in session_columns
        assert "session_key" not in session_columns
        assert {
            "story_prompt",
            "first_message",
            "main_llm_provider_key",
        }.issubset(story_columns)
        assert "narrative_outcome_weights_json" not in story_columns
        assert "description" not in story_columns
        assert {
            "session_id",
            "title",
            "description",
            "main_llm_provider_key",
            "player_character_id",
            "player_character_snapshot_json",
        }.issubset(profile_columns)
        assert "narrative_outcome_weights_json" not in profile_columns
        catalog_names = {
            row["module_name"]
            for row in conn.execute("SELECT module_name FROM rpg_rp_module_catalog")
        }
        assert catalog_names == {"narrative_outcome", "dice"}
        mounted = {
            row["module_name"]
            for row in conn.execute(
                "SELECT module_name FROM rpg_story_rp_modules WHERE story_id = 1"
            )
        }
        assert mounted == catalog_names
        assert {
            "session_id",
            "role",
            "content",
            "turn_id",
            "seq_in_turn",
            "tool_call_id",
            "tool_calls_json",
            "mode",
        }.issubset(session_message_columns)
        assert "mode" in backup_message_columns
        assert session_message_info["mode"]["notnull"] == 1
        assert session_message_info["mode"]["dflt_value"] == "'ic'"
        assert {
            "summary_processed",
            "summary_batch_id",
            "summary_processed_at",
            "story_memory_processed",
            "story_memory_processed_at",
        }.issubset(session_message_columns)
        assert session_message_info["turn_id"]["notnull"] == 1
        assert session_message_info["seq_in_turn"]["notnull"] == 1
        assert session_message_info["turn_id"]["dflt_value"] is None
        assert session_message_info["seq_in_turn"]["dflt_value"] is None
        assert session_message_info["summary_processed_at"]["type"].upper() == "TEXT"
        assert session_message_info["story_memory_processed_at"]["type"].upper() == "TEXT"
        assert {
            "summary_processed",
            "summary_batch_id",
            "summary_processed_at",
            "story_memory_processed",
            "story_memory_processed_at",
        }.isdisjoint(backup_message_columns)
        assert "hid" not in session_message_columns
        assert {
            "session_id",
            "turn_id",
            "text",
            "memory_kind",
            "epistemic_status",
            "salience",
            "source_turn_start",
            "source_turn_end",
            "dedupe_key",
            "dream_processed",
            "metadata_schema_version",
            "metadata_json",
            "source_messages_manifest_json",
        }.issubset(story_memory_columns)
        assert {
            "proposal_id",
            "action",
            "target_memory_id",
            "base_revision_number",
            "dedupe_key",
            "selected",
            "text",
            "memory_kind",
            "epistemic_status",
            "salience",
            "reason",
        }.issubset(dream_item_columns)
        assert {
            "session_id",
            "turn_id",
            "outcome_code",
            "reason",
            "actor",
            "sample_value",
            "effective_weights_json",
            "effective_source",
        }.issubset(narrative_outcome_columns)
        assert "last_story_rp_his_id" not in session_columns
        assert "enabled" not in character_columns
        assert "enabled" not in character_detail_columns
        assert "enabled" not in lorebook_columns
        assert "enabled" not in story_character_columns
        assert "enabled" not in story_lorebook_columns
        assert {"status_kind", "document_json"}.issubset(status_template_columns)
        assert {"story_character_mount_id", "mount_origin"}.issubset(story_status_columns)
        assert {"status_kind", "document_json", "origin", "source_table_id"}.issubset(session_status_columns)
        assert "relative_path" not in status_template_columns
        assert "relative_path" not in session_status_columns
        assert "headers_json" not in status_template_columns
        assert "rows_json" not in status_template_columns
        assert "headers_json" not in session_status_columns
        assert "rows_json" not in session_status_columns

        indexes = {
            row["name"]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                """
            )
        }
        assert {
            "idx_rpg_session_messages_session_id_id",
            "idx_rpg_session_messages_turn",
            "ux_rpg_session_messages_turn_seq",
            "idx_rpg_session_messages_summary_cursor",
            "idx_rpg_session_messages_story_cursor",
            "idx_rpg_session_backup_messages_session_id_id",
            "idx_rpg_session_backup_messages_turn",
            "idx_rpg_session_story_memories_session_id_id",
            "idx_rpg_session_story_memories_turn",
            "idx_rpg_session_story_memories_dream",
            "idx_rpg_session_narrative_outcomes_session_turn",
            "idx_rpg_story_narrative_styles_story",
            "ux_rpg_story_narrative_styles_base",
            "idx_rpg_story_quick_replies_story",
        }.issubset(indexes)

        assert {
            (row["mode"], row["short_name"])
            for row in conn.execute(
                "SELECT mode, short_name FROM rpg_workspace_turn_modes WHERE workspace_id = 'demo_workspace'"
            )
        } == {("ic", "角色内"), ("ooc", "场外"), ("gm", "主持")}
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_narrative_styles WHERE workspace_id = 'demo_workspace'"
        ).fetchone()["count"] == 3
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_narrative_styles WHERE story_id = 1"
        ).fetchone()["count"] == 3

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO rpg_session_messages (session_id, role, content, mode, turn_id, seq_in_turn) VALUES ('s_forest001', 'user', 'bad', 'chat', 99, 1)"
            )

        story_status_indexes = conn.execute("PRAGMA index_list(rpg_story_status_tables)").fetchall()
        for index in story_status_indexes:
            if not index["unique"]:
                continue
            columns = {
                row["name"]
                for row in conn.execute(f"PRAGMA index_info({index['name']})")
            }
            assert "story_character_mount_id" not in columns
    finally:
        conn.close()


def test_player_role_template_migration_only_repairs_untouched_demo_values(tmp_path) -> None:
    conn = db.connect(tmp_path / "role_template.sqlite3")
    try:
        run_migrations(conn)
        old_forest_message = (
            "北境森林的霜雾刚漫过石林入口，幽蓝封印在远处一明一暗。"
            "Alice 收紧斗篷，看向你：“Bob，祭坛那边又有潮声了。”"
        )
        conn.execute(
            "UPDATE rpg_stories SET first_message = ? WHERE title = ?",
            (old_forest_message, "北境森林 Demo"),
        )
        conn.execute(
            "UPDATE rpg_stories SET first_message = ? WHERE title = ?",
            ("用户自定义开场", "奥术学院 Demo"),
        )
        conn.execute(
            "UPDATE rpg_characters SET metadata_json = ? WHERE name = ?",
            ('{"kind":"demo","role":"player"}', "Bob"),
        )
        conn.execute(
            "UPDATE rpg_characters SET metadata_json = ? WHERE name = ?",
            ('{"kind":"demo","custom":true}', "Alice"),
        )
        conn.execute("DELETE FROM rpg_schema_migrations WHERE version = '0007'")
        conn.commit()

        run_migrations(conn)

        stories = {
            row["title"]: row["first_message"]
            for row in conn.execute(
                "SELECT title, first_message FROM rpg_stories WHERE workspace_id = 'demo_workspace'"
            )
        }
        metadata = {
            row["name"]: row["metadata_json"]
            for row in conn.execute(
                "SELECT name, metadata_json FROM rpg_characters WHERE workspace_id = 'demo_workspace'"
            )
        }
        assert "{USER_PLAY_ROLE_NAME}" in stories["北境森林 Demo"]
        assert stories["奥术学院 Demo"] == "用户自定义开场"
        assert metadata["Bob"] == '{"kind":"demo"}'
        assert metadata["Alice"] == '{"kind":"demo","custom":true}'
    finally:
        conn.close()


def test_run_migrations_is_idempotent() -> None:
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
            ("0004", "0004_main_llm_selection.sql"),
            ("0005", "0005_rp_modules.sql"),
            ("0006", "0006_session_composer.sql"),
            ("0007", "0007_player_role_templates.sql"),
            ("0008", "0008_status_update_frequency.sql"),
            ("0009", "0009_media.sql"),
            ("0010", "0010_media_library_backgrounds.sql"),
            ("0011", "0011_media_generated_library.sql"),
            ("0012", "0012_media_library_taxonomy.sql"),
            ("0013", "0013_tts.sql"),
            ("0014", "0014_story_memory_metadata.sql"),
            ("0015", "0015_dream_memory.sql"),
        ]
    finally:
        conn.close()


def test_story_memory_metadata_migration_hard_cuts_legacy_rows(monkeypatch) -> None:
    conn = db.connect(":memory:")
    migrations = migration_runner._iter_migration_files()
    story_memory_index = next(
        index
        for index, migration in enumerate(migrations)
        if migration.name == "0014_story_memory_metadata.sql"
    )
    try:
        monkeypatch.setattr(
            migration_runner,
            "_iter_migration_files",
            lambda: migrations[:story_memory_index],
        )
        migration_runner.run_migrations(conn)
        conn.execute(
            """
            INSERT INTO rpg_session_story_memories (
                session_id, turn_id, text, metadata_json
            ) VALUES ('s_forest001', 1, 'legacy memory', '{"legacy":true}')
            """
        )
        conn.commit()

        monkeypatch.setattr(
            migration_runner,
            "_iter_migration_files",
            lambda: migrations,
        )
        migration_runner.run_migrations(conn)

        assert conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_session_story_memories"
        ).fetchone()["count"] == 0
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO rpg_session_story_memories (
                    session_id, turn_id, text, source_turn_start,
                    source_turn_end, dedupe_key
                ) VALUES ('s_forest001', 1, 'invalid key', 1, 1, 'short')
                """
            )
        conn.rollback()
    finally:
        conn.close()


def test_generated_media_library_migration_backfills_existing_gallery_assets() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)
        session = conn.execute(
            "SELECT id, workspace_id, story_id FROM rpg_sessions ORDER BY id LIMIT 1"
        ).fetchone()
        assert session is not None
        with db.transaction(conn):
            conn.execute(
                """
                INSERT INTO rpg_media_blobs (
                    id, workspace_id, sha256, canonical_ext, mime_type,
                    byte_size, relative_path
                ) VALUES (?, ?, ?, 'png', 'image/png', 128, ?)
                """,
                (
                    "legacy_generated_blob",
                    session["workspace_id"],
                    "a" * 64,
                    f"assets/images/{'a' * 64}.png",
                ),
            )
            conn.execute(
                """
                INSERT INTO rpg_media_assets (
                    id, workspace_id, blob_id, provider_key,
                    visual_brief_json, origin_kind
                ) VALUES (?, ?, ?, 'legacy_provider', ?, 'generated')
                """,
                (
                    "legacy_generated_asset",
                    session["workspace_id"],
                    "legacy_generated_blob",
                    '{"sceneDescription":"Moonlit legacy forest"}',
                ),
            )
            conn.execute(
                """
                INSERT INTO rpg_session_media_gallery_items (
                    id, session_id, asset_id, source_start_turn_id,
                    source_end_turn_id, source_fingerprint,
                    source_snapshot_json, visual_brief_json
                ) VALUES (?, ?, ?, 1, 1, ?, '{}', ?)
                """,
                (
                    "legacy_generated_gallery",
                    session["id"],
                    "legacy_generated_asset",
                    "b" * 64,
                    '{"sceneDescription":"Moonlit legacy forest"}',
                ),
            )
            conn.execute(
                "DELETE FROM rpg_schema_migrations WHERE version = '0011'"
            )

        run_migrations(conn)

        item = conn.execute(
            """
            SELECT scope, story_id, title, description
            FROM rpg_media_library_items
            WHERE asset_id = 'legacy_generated_asset'
            """
        ).fetchone()
        assert item is not None
        assert item["scope"] == "story"
        assert item["story_id"] == session["story_id"]
        assert item["title"] == "Moonlit legacy forest"
        assert item["description"] == "Moonlit legacy forest"
        tag = conn.execute(
            """
            SELECT tag
            FROM rpg_media_library_item_tags
            WHERE item_id = (
                SELECT id FROM rpg_media_library_items
                WHERE asset_id = 'legacy_generated_asset'
            )
            """
        ).fetchone()
        assert tag is not None and tag["tag"] == "generated"
    finally:
        conn.close()


def test_initial_schema_enforces_foreign_keys() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        with db.transaction(conn):
            conn.execute(
                """
                INSERT INTO rpg_characters (workspace_id, name, content)
                VALUES ('demo_workspace', 'Test Alice', 'A young wizard.')
                """
            )
            character_id = conn.execute("SELECT id FROM rpg_characters").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO rpg_character_details (character_id, name, content, tags_json)
                VALUES (?, '外貌', '银白色长发。', '["外观"]')
                """,
                (character_id,),
            )

        try:
            with db.transaction(conn):
                conn.execute(
                    """
                    INSERT INTO rpg_lorebook_entries (workspace_id, name, content)
                    VALUES ('missing', 'World History', 'Forged from ashes.')
                    """
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected missing workspace foreign key to fail")

        with db.transaction(conn):
            conn.execute(
                """
                INSERT INTO rpg_session_messages (session_id, role, content, turn_id, seq_in_turn)
                VALUES ('s_forest001', 'user', 'hello', 100, 1)
                """
            )
            conn.execute(
                """
                INSERT INTO rpg_session_backup_messages (session_id, role, content, turn_id, seq_in_turn)
                VALUES ('s_forest001', 'assistant', 'world', 100, 2)
                """
            )

        try:
            with db.transaction(conn):
                conn.execute(
                    """
                    INSERT INTO rpg_session_messages (session_id, role, content)
                    VALUES ('s_forest001', 'user', 'missing turn')
                    """
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected missing turn metadata to fail")

        try:
            with db.transaction(conn):
                conn.execute(
                    """
                    INSERT INTO rpg_session_messages (session_id, role, content, turn_id, seq_in_turn)
                    VALUES ('s_forest001', 'user', 'duplicate turn seq', 100, 1)
                    """
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected duplicate main turn seq to fail")

        with db.transaction(conn):
            conn.execute(
                """
                INSERT INTO rpg_session_backup_messages (session_id, role, content, turn_id, seq_in_turn)
                VALUES ('s_forest001', 'user', 'backup duplicate turn seq', 100, 2)
                """
            )

        try:
            with db.transaction(conn):
                conn.execute(
                    """
                    INSERT INTO rpg_session_messages (session_id, role, content, turn_id, seq_in_turn)
                    VALUES ('s_forest001', 'bad_role', 'hello', 101, 1)
                    """
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected invalid message role to fail")

        try:
            with db.transaction(conn):
                conn.execute(
                    """
                    INSERT INTO rpg_session_backup_messages (session_id, role, content, turn_id, seq_in_turn)
                    VALUES ('missing_session', 'user', 'hello', 1, 1)
                    """
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected missing session foreign key to fail")
    finally:
        conn.close()


def test_initial_schema_does_not_create_default_workspace() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        row = conn.execute("SELECT id FROM rpg_workspaces WHERE id = 'default'").fetchone()

        assert row is None
    finally:
        conn.close()


def test_workspace_supports_multiple_stories_and_shared_mounts() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        with db.transaction(conn):
            conn.execute(
                """
                INSERT INTO rpg_workspaces (id, name, root_path)
                VALUES ('multi_workspace', 'Multi Workspace', 'data/multi_workspace')
                """
            )
            story_ids = []
            for title in ("北境森林", "学院旧梦"):
                conn.execute(
                    """
                    INSERT INTO rpg_stories (workspace_id, title)
                    VALUES ('multi_workspace', ?)
                    """,
                    (title,),
                )
                story_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            conn.execute(
                """
                INSERT INTO rpg_characters (workspace_id, name, content)
                VALUES ('multi_workspace', 'Alice', 'A young wizard.')
                """
            )
            character_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                """
                INSERT INTO rpg_lorebook_entries (workspace_id, name, content)
                VALUES ('multi_workspace', 'World History', 'Forged from ashes.')
                """
            )
            lorebook_entry_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            for index, story_id in enumerate(story_ids, start=1):
                conn.execute(
                    """
                    INSERT INTO rpg_sessions (id, workspace_id, story_id)
                    VALUES (?, 'multi_workspace', ?)
                    """,
                    (f"multi_session_{index}", story_id),
                )
                conn.execute(
                    """
                    INSERT INTO rpg_session_profiles (session_id, title)
                    VALUES (?, ?)
                    """,
                    (f"multi_session_{index}", f"Session {index}"),
                )
                conn.execute(
                    """
                    INSERT INTO rpg_story_characters (workspace_id, story_id, character_id)
                    VALUES ('multi_workspace', ?, ?)
                    """,
                    (story_id, character_id),
                )
                conn.execute(
                    """
                    INSERT INTO rpg_story_lorebook_entries (
                        workspace_id,
                        story_id,
                        lorebook_entry_id
                    )
                    VALUES ('multi_workspace', ?, ?)
                    """,
                    (story_id, lorebook_entry_id),
                )

        story_count = conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_stories WHERE workspace_id = 'multi_workspace'"
        ).fetchone()["count"]
        character_mount_count = conn.execute(
            "SELECT COUNT(*) AS count FROM rpg_story_characters WHERE character_id = ?",
            (character_id,),
        ).fetchone()["count"]
        lorebook_mount_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_story_lorebook_entries
            WHERE lorebook_entry_id = ?
            """,
            (lorebook_entry_id,),
        ).fetchone()["count"]
        session_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_sessions
            WHERE workspace_id = 'multi_workspace'
            """
        ).fetchone()["count"]

        assert story_count == 2
        assert session_count == 2
        assert character_mount_count == 2
        assert lorebook_mount_count == 2

        try:
            with db.transaction(conn):
                conn.execute(
                    """
                    INSERT INTO rpg_sessions (id, workspace_id, story_id)
                    VALUES ('multi_session_1', 'multi_workspace', ?)
                    """,
                    (story_ids[1],),
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected duplicate session id to fail")
    finally:
        conn.close()


def test_demo_migration_creates_demo_workspace_data() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        workspace = conn.execute(
            """
            SELECT id, name, root_path
            FROM rpg_workspaces
            WHERE id = 'demo_workspace'
            """
        ).fetchone()
        story_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_stories
            WHERE workspace_id = 'demo_workspace'
            """
        ).fetchone()["count"]
        session_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_sessions
            WHERE workspace_id = 'demo_workspace'
            """
        ).fetchone()["count"]
        profile_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_session_profiles
            WHERE session_id IN (
                SELECT id
                FROM rpg_sessions
                WHERE workspace_id = 'demo_workspace'
            )
            """
        ).fetchone()["count"]
        character_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_characters
            WHERE workspace_id = 'demo_workspace'
            """
        ).fetchone()["count"]
        character_detail_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_character_details
            WHERE character_id IN (
                SELECT id
                FROM rpg_characters
                WHERE workspace_id = 'demo_workspace'
            )
            """
        ).fetchone()["count"]
        lorebook_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_lorebook_entries
            WHERE workspace_id = 'demo_workspace'
            """
        ).fetchone()["count"]
        character_mount_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_story_characters
            WHERE workspace_id = 'demo_workspace'
            """
        ).fetchone()["count"]
        lorebook_mount_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_story_lorebook_entries
            WHERE workspace_id = 'demo_workspace'
            """
        ).fetchone()["count"]
        status_template_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_status_table_templates
            WHERE workspace_id = 'demo_workspace'
            """
        ).fetchone()["count"]
        status_mount_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_story_status_tables
            WHERE workspace_id = 'demo_workspace'
            """
        ).fetchone()["count"]
        scene_template = conn.execute(
            """
            SELECT status_kind, document_json, metadata_json
            FROM rpg_status_table_templates
            WHERE workspace_id = 'demo_workspace'
              AND name = '北境森林当前场景'
            """
        ).fetchone()

        assert dict(workspace) == {
            "id": "demo_workspace",
            "name": "Demo Workspace",
            "root_path": "data/demo_workspace",
        }
        assert story_count == 3
        assert session_count == 3
        assert profile_count == 3
        assert character_count == 2
        assert character_detail_count == 2
        assert lorebook_count == 2
        assert character_mount_count == 5
        assert lorebook_mount_count == 4
        assert status_template_count == 3
        assert status_mount_count == 4
        assert scene_template["status_kind"] == "scene"
        assert '"runtimeKeyLocked":true' in scene_template["document_json"]
        assert '"_bootstrap_csv"' not in scene_template["metadata_json"]
    finally:
        conn.close()


def test_pagination_demo_migration_creates_long_history_session() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        story = conn.execute(
            """
            SELECT id, title, story_prompt, first_message, metadata_json
            FROM rpg_stories
            WHERE workspace_id = 'demo_workspace'
              AND title = '分页压力测试 Demo'
            """
        ).fetchone()
        session = conn.execute(
            """
            SELECT id, story_id, state_json
            FROM rpg_sessions
            WHERE id = 's_pagination001'
            """
        ).fetchone()
        profile = conn.execute(
            """
            SELECT title, player_character_id, player_character_snapshot_json
            FROM rpg_session_profiles
            WHERE session_id = 's_pagination001'
            """
        ).fetchone()
        main_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_session_messages
            WHERE session_id = 's_pagination001'
            """
        ).fetchone()["count"]
        backup_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_session_backup_messages
            WHERE session_id = 's_pagination001'
            """
        ).fetchone()["count"]
        turn_count = conn.execute(
            """
            SELECT COUNT(DISTINCT turn_id) AS count
            FROM rpg_session_messages
            WHERE session_id = 's_pagination001'
            """
        ).fetchone()["count"]
        first_messages = conn.execute(
            """
            SELECT role, content, turn_id, seq_in_turn
            FROM rpg_session_messages
            WHERE session_id = 's_pagination001'
            ORDER BY turn_id, seq_in_turn
            LIMIT 2
            """
        ).fetchall()
        latest_messages = conn.execute(
            """
            SELECT role, content, turn_id, seq_in_turn
            FROM rpg_session_messages
            WHERE session_id = 's_pagination001'
              AND turn_id = 160
            ORDER BY seq_in_turn
            """
        ).fetchall()

        assert story is not None
        assert story["metadata_json"] == '{"kind":"pagination_demo","order":99,"purpose":"history_pagination"}'
        assert "分页测试专用背景" in story["story_prompt"]
        assert "分页" in story["first_message"]
        assert dict(session) == {
            "id": "s_pagination001",
            "story_id": story["id"],
            "state_json": '{"scene":"分页测试·长历史记录","time":"分页测试第 1 页"}',
        }
        assert profile["title"] == "分页压力测试长历史"
        assert profile["player_character_id"] is not None
        assert '"name":"Bob"' in profile["player_character_snapshot_json"]
        assert f'"storyId":{story["id"]}' in profile["player_character_snapshot_json"]
        assert main_count == 320
        assert backup_count == 320
        assert turn_count == 160
        assert [dict(row) for row in first_messages] == [
            {"role": "user", "content": "分页测试 user turn 001", "turn_id": 1, "seq_in_turn": 1},
            {"role": "assistant", "content": "分页测试 assistant turn 001", "turn_id": 1, "seq_in_turn": 2},
        ]
        assert [dict(row) for row in latest_messages] == [
            {"role": "user", "content": "分页测试 user turn 160", "turn_id": 160, "seq_in_turn": 1},
            {"role": "assistant", "content": "分页测试 assistant turn 160", "turn_id": 160, "seq_in_turn": 2},
        ]
    finally:
        conn.close()
