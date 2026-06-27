from __future__ import annotations

from pathlib import Path

from peewee import SqliteDatabase

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.repositories.lorebook_repo import LorebookEntryRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_lorebook_repo import StoryLorebookEntryRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services.lorebook import LorebookReadService


def _migrated_database(tmp_path: Path) -> SqliteDatabase:
    db_path = tmp_path / "lorebook_service.sqlite3"
    conn = db.connect(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()

    database = db.bind_peewee_database(db.make_peewee_database(db_path))
    database.connect()
    return database


def test_lorebook_read_service_lists_session_story_mounts(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)
        sessions = SessionRepository(database)
        lorebooks = LorebookEntryRepository(database)
        mounts = StoryLorebookEntryRepository(database)

        with database.atomic():
            workspaces.create("main_ws", "Main", "data/main_ws")
            workspaces.create("other_ws", "Other", "data/other_ws")
            main_story = stories.create("main_ws", "Main Story")
            side_story = stories.create("main_ws", "Side Story")
            other_story = stories.create("other_ws", "Other Story")
            main_session = sessions.create("main_ws", main_story.id, session_id="s_main")
            side_session = sessions.create("main_ws", side_story.id, session_id="s_side")
            other_session = sessions.create("other_ws", other_story.id, session_id="s_other")

            first = lorebooks.create(
                "main_ws",
                "First",
                content="First content",
                description="First desc",
                tags_json='["alpha", "beta"]',
            )
            second = lorebooks.create(
                "main_ws",
                "Second",
                content="Second content",
                tags_json="{bad json",
            )
            unmounted = lorebooks.create("main_ws", "Unmounted", content="Hidden")
            side_only = lorebooks.create("main_ws", "Side Only", content="Side")
            other_only = lorebooks.create("other_ws", "Other Only", content="Other")

            mounts.create("main_ws", main_story.id, second.id, sort_order=20)
            mounts.create("main_ws", main_story.id, first.id, sort_order=10)
            mounts.create("main_ws", side_story.id, side_only.id, sort_order=1)
            mounts.create("other_ws", other_story.id, other_only.id, sort_order=1)

        service = LorebookReadService(database)

        all_entries = service.list_entries(main_session.id)
        assert [entry.name for entry in all_entries] == ["First", "Second"]
        assert [entry.sort_order for entry in all_entries] == [10, 20]
        assert all_entries[0].tags == ("alpha", "beta")
        assert all_entries[1].tags == ()
        assert all_entries[0].workspace_id == "main_ws"
        assert all_entries[0].story_id == main_story.id

        enabled_entries = service.list_enabled_entries(main_session.id)
        assert [entry.name for entry in enabled_entries] == ["First", "Second"]
        assert service.list_enabled_entries(side_session.id)[0].name == "Side Only"
        assert service.list_enabled_entries(other_session.id)[0].name == "Other Only"

        assert service.get_entry(main_session.id, "First").content == "First content"
        assert service.get_entry(main_session.id, unmounted.name) is None
        assert service.get_entry(main_session.id, "Side Only") is None
        assert service.list_entries("missing_session") == []
        assert service.get_entry("missing_session", "First") is None
    finally:
        database.close()
