from __future__ import annotations

from pathlib import Path

import pytest
from peewee import IntegrityError, SqliteDatabase

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_lorebook_repo import StoryLorebookEntryRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services.lorebook import LorebookManagementService, LorebookReadService


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


def test_lorebook_read_service_lists_only_session_story_entries(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)
        sessions = SessionRepository(database)
        entries = StoryLorebookEntryRepository(database)
        with database.atomic():
            workspaces.create("main_ws", "Main", "data/main_ws")
            main_story = stories.create("main_ws", "Main Story")
            side_story = stories.create("main_ws", "Side Story")
            main_session = sessions.create("main_ws", main_story.id, session_id="s_main")
            side_session = sessions.create("main_ws", side_story.id, session_id="s_side")
            entries.create("main_ws", main_story.id, "Second", tags_json="{bad", sort_order=20)
            entries.create(
                "main_ws", main_story.id, "First", content="Main", tags_json='["alpha"]', sort_order=10
            )
            entries.create("main_ws", side_story.id, "First", content="Side", sort_order=10)

        service = LorebookReadService(database)
        main = service.list_entries(main_session.id)
        assert [entry.name for entry in main] == ["First", "Second"]
        assert main[0].tags == ("alpha",)
        assert main[1].tags == ()
        assert service.get_entry(main_session.id, "First").content == "Main"
        assert service.get_entry(side_session.id, "First").content == "Side"
        assert service.list_entries("missing") == []
    finally:
        database.close()


def test_lorebook_management_service_manages_story_entries(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)
        with database.atomic():
            workspaces.create("main_ws", "Main", "data/main_ws")
            story = stories.create("main_ws", "Main Story")
            other_story = stories.create("main_ws", "Other Story")
        service = LorebookManagementService(database)

        created = service.create_entry(
            "main_ws",
            story.id,
            name="Harbor Bell",
            content="The thirteenth ring is a warning.",
            description="A local legend.",
            tags=["place", " myth ", ""],
            sort_order=10,
            metadata={"ui": {"displayVersion": "v1.0.0"}},
        )
        assert created is not None
        assert created.story_id == story.id
        assert created.tags_json == '["place", "myth"]'
        assert service.create_entry("main_ws", 99999, name="Hidden") is None
        same_name = service.create_entry("main_ws", other_story.id, name="Harbor Bell")
        assert same_name is not None
        with pytest.raises(IntegrityError):
            service.create_entry("main_ws", story.id, name="Harbor Bell")

        updated = service.update_entry(
            "main_ws",
            story.id,
            created.id,
            name="Harbor Bell Revised",
            tags=["place"],
            metadata={"ui": {"displayVersion": "v1.0.1"}},
        )
        assert updated is not None
        assert updated.name == "Harbor Bell Revised"
        assert updated.tags_json == '["place"]'
        assert updated.version == 2
        assert service.update_entry(
            "main_ws", other_story.id, created.id, name="Wrong"
        ) is None
        assert service.delete_entry("main_ws", story.id, created.id) is True
        assert service.delete_entry("main_ws", story.id, created.id) is False
        assert service.list_entries("main_ws", story.id) == []
        assert service.list_entries("main_ws", other_story.id) == [same_name]
    finally:
        database.close()
