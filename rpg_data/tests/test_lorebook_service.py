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


def test_lorebook_management_service_manages_entries_and_mounts(tmp_path: Path) -> None:
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
            name="Harbor Bell",
            content="The thirteenth ring is a warning.",
            description="A local legend.",
            tags=["place", " myth ", ""],
            metadata={"ui": {"displayVersion": "v1.0.0"}},
        )
        assert created is not None
        assert created.name == "Harbor Bell"
        assert created.tags_json == '["place", "myth"]'
        assert created.metadata_json == '{"ui": {"displayVersion": "v1.0.0"}}'
        assert service.create_entry("missing_ws", name="Hidden") is None

        listed = service.list_entries("main_ws")
        assert listed is not None
        assert [entry.name for entry in listed] == ["Harbor Bell"]
        assert service.list_entries("missing_ws") is None

        updated = service.update_entry(
            "main_ws",
            int(created.id),
            name="Harbor Bell Revised",
            tags=["place"],
            metadata={"ui": {"displayVersion": "v1.0.1"}},
        )
        assert updated is not None
        assert updated.name == "Harbor Bell Revised"
        assert updated.tags_json == '["place"]'
        assert updated.version == 2
        assert service.update_entry("other_ws", int(created.id), name="Nope") is None

        mounted = service.mount_entry("main_ws", story.id, int(created.id))
        assert mounted is not None
        assert mounted.mount.id is not None
        assert mounted.mount.story_id == story.id
        assert mounted.entry.name == "Harbor Bell Revised"

        duplicate = service.mount_entry("main_ws", story.id, int(created.id))
        assert duplicate is not None
        assert duplicate.mount.id == mounted.mount.id

        assert service.list_story_entries("main_ws", story.id)[0].entry.name == "Harbor Bell Revised"
        assert service.list_story_entries("main_ws", other_story.id) == []
        assert service.list_story_entries("main_ws", 99999) is None

        assert service.unmount_entry("main_ws", story.id, int(mounted.mount.id)) is True
        assert service.unmount_entry("main_ws", story.id, int(mounted.mount.id)) is False
        assert service.list_story_entries("main_ws", story.id) == []

        remounted = service.mount_entry("main_ws", story.id, int(created.id))
        assert remounted is not None
        assert service.delete_entry("main_ws", int(created.id)) is True
        assert service.delete_entry("main_ws", int(created.id)) is False
        assert service.list_entries("main_ws") == []
        assert service.list_story_entries("main_ws", story.id) == []
    finally:
        database.close()
