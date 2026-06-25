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
            "schema_migrations",
            "workspaces",
            "stories",
            "sessions",
            "characters",
            "character_details",
            "lorebook_entries",
            "story_characters",
            "story_lorebook_entries",
        }.issubset(tables)

        for table in (
            "workspaces",
            "stories",
            "sessions",
            "characters",
            "character_details",
            "lorebook_entries",
            "story_characters",
            "story_lorebook_entries",
        ):
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert {"created_at", "updated_at", "version"}.issubset(columns)

        session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
        character_columns = {row["name"] for row in conn.execute("PRAGMA table_info(characters)")}
        lorebook_columns = {row["name"] for row in conn.execute("PRAGMA table_info(lorebook_entries)")}

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
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

        assert [(row["version"], row["name"]) for row in rows] == [
            ("0001", "0001_initial.sql")
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
                INSERT INTO characters (workspace_id, name, content)
                VALUES ('default', 'Alice', 'A young wizard.')
                """
            )
            character_id = conn.execute("SELECT id FROM characters").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO character_details (character_id, name, content, tags_json)
                VALUES (?, '外貌', '银白色长发。', '["外观"]')
                """,
                (character_id,),
            )

        try:
            with db.transaction(conn):
                conn.execute(
                    """
                    INSERT INTO lorebook_entries (workspace_id, name, content)
                    VALUES ('missing', 'World History', 'Forged from ashes.')
                    """
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected missing workspace foreign key to fail")
    finally:
        conn.close()


def test_initial_schema_creates_default_data_workspace() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        row = conn.execute(
            "SELECT id, name, root_path FROM workspaces WHERE id = 'default'"
        ).fetchone()

        assert dict(row) == {
            "id": "default",
            "name": "Default",
            "root_path": "data",
        }
    finally:
        conn.close()


def test_workspace_supports_multiple_stories_and_shared_mounts() -> None:
    conn = db.connect(":memory:")
    try:
        run_migrations(conn)

        with db.transaction(conn):
            story_ids = []
            for title in ("北境森林", "学院旧梦"):
                conn.execute(
                    """
                    INSERT INTO stories (workspace_id, title)
                    VALUES ('default', ?)
                    """,
                    (title,),
                )
                story_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            conn.execute(
                """
                INSERT INTO characters (workspace_id, name, content)
                VALUES ('default', 'Alice', 'A young wizard.')
                """
            )
            character_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                """
                INSERT INTO lorebook_entries (workspace_id, name, content)
                VALUES ('default', 'World History', 'Forged from ashes.')
                """
            )
            lorebook_entry_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            for story_id in story_ids:
                conn.execute(
                    """
                    INSERT INTO story_characters (workspace_id, story_id, character_id)
                    VALUES ('default', ?, ?)
                    """,
                    (story_id, character_id),
                )
                conn.execute(
                    """
                    INSERT INTO story_lorebook_entries (
                        workspace_id,
                        story_id,
                        lorebook_entry_id
                    )
                    VALUES ('default', ?, ?)
                    """,
                    (story_id, lorebook_entry_id),
                )

        story_count = conn.execute(
            "SELECT COUNT(*) AS count FROM stories WHERE workspace_id = 'default'"
        ).fetchone()["count"]
        character_mount_count = conn.execute(
            "SELECT COUNT(*) AS count FROM story_characters WHERE character_id = ?",
            (character_id,),
        ).fetchone()["count"]
        lorebook_mount_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM story_lorebook_entries
            WHERE lorebook_entry_id = ?
            """,
            (lorebook_entry_id,),
        ).fetchone()["count"]

        assert story_count == 2
        assert character_mount_count == 2
        assert lorebook_mount_count == 2
    finally:
        conn.close()
