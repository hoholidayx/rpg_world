from __future__ import annotations

import sqlite3

from rpg_data import db
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
            "rpg_characters",
            "rpg_character_details",
            "rpg_lorebook_entries",
            "rpg_story_characters",
            "rpg_story_lorebook_entries",
            "rpg_status_types",
            "rpg_status_table_templates",
            "rpg_story_status_tables",
            "rpg_session_status_types",
            "rpg_session_status_tables",
        }.issubset(tables)

        for table in (
            "rpg_workspaces",
            "rpg_stories",
            "rpg_sessions",
            "rpg_session_profiles",
            "rpg_session_messages",
            "rpg_session_backup_messages",
            "rpg_characters",
            "rpg_character_details",
            "rpg_lorebook_entries",
            "rpg_story_characters",
            "rpg_story_lorebook_entries",
            "rpg_status_types",
            "rpg_status_table_templates",
            "rpg_story_status_tables",
            "rpg_session_status_types",
            "rpg_session_status_tables",
        ):
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert {"created_at", "updated_at", "version"}.issubset(columns)

        session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_sessions)")}
        session_message_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_session_messages)")}
        backup_message_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_session_backup_messages)")}
        character_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_characters)")}
        character_detail_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_character_details)")}
        lorebook_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_lorebook_entries)")}
        story_character_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_story_characters)")}
        story_lorebook_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_story_lorebook_entries)")}
        status_template_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_status_table_templates)")}
        session_status_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_session_status_tables)")}

        profile_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_session_profiles)")}

        assert "last_story_turn_index" in session_columns
        assert "session_key" not in session_columns
        assert {"session_id", "title", "description"}.issubset(profile_columns)
        assert {
            "session_id",
            "role",
            "content",
            "turn_id",
            "seq_in_turn",
            "tool_call_id",
            "tool_calls_json",
        }.issubset(session_message_columns)
        assert session_message_columns == backup_message_columns
        assert "hid" not in session_message_columns
        assert "last_story_rp_his_id" not in session_columns
        assert "enabled" not in character_columns
        assert "enabled" not in character_detail_columns
        assert "enabled" not in lorebook_columns
        assert "enabled" not in story_character_columns
        assert "enabled" not in story_lorebook_columns
        assert "relative_path" in status_template_columns
        assert "relative_path" in session_status_columns
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
            "idx_rpg_session_backup_messages_session_id_id",
            "idx_rpg_session_backup_messages_turn",
        }.issubset(indexes)
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
        ]
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
                INSERT INTO rpg_session_messages (session_id, role, content)
                VALUES ('s_forest001', 'user', 'hello')
                """
            )
            conn.execute(
                """
                INSERT INTO rpg_session_backup_messages (session_id, role, content)
                VALUES ('s_forest001', 'assistant', 'world')
                """
            )

        try:
            with db.transaction(conn):
                conn.execute(
                    """
                    INSERT INTO rpg_session_messages (session_id, role, content)
                    VALUES ('s_forest001', 'bad_role', 'hello')
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
                    INSERT INTO rpg_session_backup_messages (session_id, role, content)
                    VALUES ('missing_session', 'user', 'hello')
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
        status_type_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rpg_status_types
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
            SELECT relative_path, metadata_json
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
        assert story_count == 2
        assert session_count == 2
        assert profile_count == 2
        assert character_count == 2
        assert character_detail_count == 2
        assert lorebook_count == 2
        assert character_mount_count == 4
        assert lorebook_mount_count == 4
        assert status_type_count == 2
        assert status_template_count == 3
        assert status_mount_count == 4
        assert scene_template["relative_path"] == "template_status/场景/北境森林当前场景.csv"
        assert '"_bootstrap_csv"' in scene_template["metadata_json"]
    finally:
        conn.close()
