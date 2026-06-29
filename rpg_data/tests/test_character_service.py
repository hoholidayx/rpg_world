from __future__ import annotations

from pathlib import Path

from peewee import SqliteDatabase

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.repositories.character_detail_repo import CharacterDetailRepository
from rpg_data.repositories.character_repo import CharacterRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_character_repo import StoryCharacterRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services.character import CharacterManagementService, CharacterReadService


def _migrated_database(tmp_path: Path) -> SqliteDatabase:
    db_path = tmp_path / "character_service.sqlite3"
    conn = db.connect(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()

    database = db.bind_peewee_database(db.make_peewee_database(db_path))
    database.connect()
    return database


def test_character_read_service_lists_session_story_mounts(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)
        sessions = SessionRepository(database)
        characters = CharacterRepository(database)
        details = CharacterDetailRepository(database)
        mounts = StoryCharacterRepository(database)

        with database.atomic():
            workspaces.create("main_ws", "Main", "data/main_ws")
            workspaces.create("other_ws", "Other", "data/other_ws")
            main_story = stories.create("main_ws", "Main Story")
            side_story = stories.create("main_ws", "Side Story")
            other_story = stories.create("other_ws", "Other Story")
            main_session = sessions.create("main_ws", main_story.id, session_id="s_main")
            side_session = sessions.create("main_ws", side_story.id, session_id="s_side")
            other_session = sessions.create("other_ws", other_story.id, session_id="s_other")

            first = characters.create(
                "main_ws",
                "First",
                personality="calm",
                content="First content",
            )
            second = characters.create(
                "main_ws",
                "Second",
                personality="bold",
                content="Second content",
            )
            unmounted = characters.create("main_ws", "Unmounted", content="Hidden")
            side_only = characters.create("main_ws", "Side Only", content="Side")
            other_only = characters.create("other_ws", "Other Only", content="Other")

            details.create(first.id, "A", content="A detail", tags_json='["alpha"]', sort_order=20)
            details.create(first.id, "B", content="B detail", tags_json="{bad json", sort_order=10)
            details.create(unmounted.id, "Hidden Detail", content="Hidden")

            mounts.create("main_ws", main_story.id, second.id, sort_order=20)
            mounts.create("main_ws", main_story.id, first.id, sort_order=10)
            mounts.create("main_ws", side_story.id, side_only.id, sort_order=1)
            mounts.create("other_ws", other_story.id, other_only.id, sort_order=1)

        service = CharacterReadService(database)

        main_characters = service.list_characters(main_session.id)
        assert [character.name for character in main_characters] == ["First", "Second"]
        assert [character.sort_order for character in main_characters] == [10, 20]
        assert main_characters[0].workspace_id == "main_ws"
        assert main_characters[0].story_id == main_story.id
        assert main_characters[0].personality == "calm"
        assert [detail.name for detail in main_characters[0].details] == ["B", "A"]
        assert main_characters[0].details[0].tags == ()
        assert main_characters[0].details[1].tags == ("alpha",)

        assert service.list_characters(side_session.id)[0].name == "Side Only"
        assert service.list_characters(other_session.id)[0].name == "Other Only"
        assert service.get_character(main_session.id, "First").content == "First content"
        assert service.get_character(main_session.id, unmounted.name) is None
        assert service.get_character(main_session.id, "Side Only") is None
        assert service.list_characters("missing_session") == []
        assert service.get_character("missing_session", "First") is None
    finally:
        database.close()


def test_character_management_service_manages_cards_details_and_mounts(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)

        with database.atomic():
            workspaces.create("main_ws", "Main", "data/main_ws")
            workspaces.create("other_ws", "Other", "data/other_ws")
            story = stories.create("main_ws", "Main Story")
            other_story = stories.create("main_ws", "Other Story")

        service = CharacterManagementService(database)

        created = service.create_character(
            "main_ws",
            name="Harbor Watcher",
            personality="patient",
            content="Keeps the old lighthouse.",
            metadata={"ui": {"displayVersion": "v1.0.0", "roleLabel": "NPC"}},
        )
        assert created is not None
        assert created.name == "Harbor Watcher"
        assert created.metadata_json == '{"ui": {"displayVersion": "v1.0.0", "roleLabel": "NPC"}}'
        assert service.create_character("missing_ws", name="Hidden") is None

        listed = service.list_characters("main_ws")
        assert listed is not None
        assert [character.name for character in listed] == ["Harbor Watcher"]
        assert service.list_characters("missing_ws") is None

        detail = service.create_detail(
            "main_ws",
            int(created.id),
            name="禁忌话题",
            content="不愿谈起灯塔失火。",
            tags=["秘密", " memory ", ""],
            sort_order=20,
        )
        assert detail is not None
        assert detail.tags_json == '["秘密", "memory"]'
        assert service.create_detail("other_ws", int(created.id), name="Nope") is None

        updated_detail = service.update_detail(
            "main_ws",
            int(created.id),
            int(detail.id),
            name="禁忌话题修订",
            tags=["秘密"],
            sort_order=10,
        )
        assert updated_detail is not None
        assert updated_detail.name == "禁忌话题修订"
        assert updated_detail.tags_json == '["秘密"]'
        assert updated_detail.sort_order == 10
        assert updated_detail.version == 2
        assert service.update_detail("main_ws", int(created.id), 99999, name="Nope") is None

        updated = service.update_character(
            "main_ws",
            int(created.id),
            name="Harbor Watcher Revised",
            personality="watchful",
            metadata={"ui": {"displayVersion": "v1.0.1"}},
        )
        assert updated is not None
        assert updated.name == "Harbor Watcher Revised"
        assert updated.personality == "watchful"
        assert updated.version == 2
        assert service.update_character("other_ws", int(created.id), name="Nope") is None

        mounted = service.mount_character("main_ws", story.id, int(created.id))
        assert mounted is not None
        assert mounted.mount.id is not None
        assert mounted.mount.story_id == story.id
        assert mounted.character.name == "Harbor Watcher Revised"

        duplicate = service.mount_character("main_ws", story.id, int(created.id))
        assert duplicate is not None
        assert duplicate.mount.id == mounted.mount.id

        assert service.list_story_characters("main_ws", story.id)[0].character.name == "Harbor Watcher Revised"
        assert service.list_story_characters("main_ws", other_story.id) == []
        assert service.list_story_characters("main_ws", 99999) is None

        assert service.unmount_character("main_ws", story.id, int(mounted.mount.id)) is True
        assert service.unmount_character("main_ws", story.id, int(mounted.mount.id)) is False
        assert service.list_story_characters("main_ws", story.id) == []

        remounted = service.mount_character("main_ws", story.id, int(created.id))
        assert remounted is not None
        assert service.delete_character("main_ws", int(created.id)) is True
        assert service.delete_character("main_ws", int(created.id)) is False
        assert service.list_characters("main_ws") == []
        assert service.list_story_characters("main_ws", story.id) == []
        assert service.delete_detail("main_ws", int(created.id), int(detail.id)) is False
    finally:
        database.close()
