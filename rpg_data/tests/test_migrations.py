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
            "rpg_characters",
            "rpg_character_details",
            "rpg_lorebook_entries",
            "rpg_story_characters",
            "rpg_story_lorebook_entries",
        }.issubset(tables)

        for table in (
            "rpg_workspaces",
            "rpg_stories",
            "rpg_sessions",
            "rpg_characters",
            "rpg_character_details",
            "rpg_lorebook_entries",
            "rpg_story_characters",
            "rpg_story_lorebook_entries",
        ):
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert {"created_at", "updated_at", "version"}.issubset(columns)

        session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_sessions)")}
        character_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_characters)")}
        lorebook_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rpg_lorebook_entries)")}

        assert "last_story_turn_index" in session_columns
        assert "last_story_rp_his_id" not in session_columns
        assert "enabled" not in character_columns
        assert "enabled" not in lorebook_columns
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

            for story_id in story_ids:
                conn.execute(
                    """
                    INSERT INTO rpg_sessions (workspace_id, story_id, session_key)
                    VALUES ('multi_workspace', ?, 'shared_session')
                    """,
                    (story_id,),
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
              AND session_key = 'shared_session'
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
                    INSERT INTO rpg_sessions (workspace_id, story_id, session_key)
                    VALUES ('multi_workspace', ?, 'shared_session')
                    """,
                    (story_ids[0],),
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected duplicate story session key to fail")
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

        assert dict(workspace) == {
            "id": "demo_workspace",
            "name": "Demo Workspace",
            "root_path": "data/demo_workspace",
        }
        assert story_count == 2
        assert session_count == 2
        assert character_count == 2
        assert character_detail_count == 2
        assert lorebook_count == 2
        assert character_mount_count == 4
        assert lorebook_mount_count == 4
    finally:
        conn.close()
