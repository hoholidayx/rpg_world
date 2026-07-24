from __future__ import annotations

from pathlib import Path

import pytest
from peewee import IntegrityError, SqliteDatabase

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.repositories.records import StoryCharacterRecord
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


def test_character_read_service_lists_only_session_story_characters(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)
        sessions = SessionRepository(database)
        characters = StoryCharacterRepository(database)
        with database.atomic():
            workspaces.create("main_ws", "Main", "data/main_ws")
            workspaces.create("other_ws", "Other", "data/other_ws")
            main_story = stories.create("main_ws", "Main Story")
            side_story = stories.create("main_ws", "Side Story")
            other_story = stories.create("other_ws", "Other Story")
            main_session = sessions.create("main_ws", main_story.id, session_id="s_main")
            side_session = sessions.create("main_ws", side_story.id, session_id="s_side")
            other_session = sessions.create("other_ws", other_story.id, session_id="s_other")

            second = characters.create("main_ws", main_story.id, "Second", sort_order=20)
            first = characters.create(
                "main_ws",
                main_story.id,
                "First",
                description="First description",
                sort_order=10,
            )
            characters.create(
                "main_ws", side_story.id, "First", description="Side copy"
            )
            characters.create(
                "other_ws", other_story.id, "First", description="Other copy"
            )
            characters.create_detail(first.id, "A", tags_json='["alpha"]', sort_order=20)
            characters.create_detail(first.id, "B", tags_json="{bad json", sort_order=10)

        service = CharacterReadService(database)
        main = service.list_characters(main_session.id)
        assert [item.name for item in main] == ["First", "Second"]
        assert [item.id for item in main] == [first.id, second.id]
        assert main[0].workspace_id == "main_ws"
        assert main[0].story_id == main_story.id
        assert [detail.name for detail in main[0].details] == ["B", "A"]
        assert main[0].details[0].tags == ()
        assert main[0].details[1].tags == ("alpha",)
        assert (
            service.get_character(main_session.id, "First").description
            == "First description"
        )
        assert service.get_character(side_session.id, "First").description == "Side copy"
        assert (
            service.get_character(other_session.id, "First").description
            == "Other copy"
        )
        assert service.list_characters("missing") == []
    finally:
        database.close()


def test_character_management_service_manages_story_cards_and_details(tmp_path: Path) -> None:
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
            story.id,
            name="Harbor Watcher",
            description="Keeps the old lighthouse.",
            sort_order=20,
            metadata={"ui": {"roleLabel": "NPC"}},
        )
        assert created is not None
        assert created.story_id == story.id
        assert created.metadata_json == '{"ui": {"roleLabel": "NPC"}}'
        assert service.create_character("main_ws", 99999, name="Hidden") is None
        assert service.list_characters("main_ws", story.id) == [created]
        assert service.list_characters("main_ws", 99999) is None

        same_name_other_story = service.create_character(
            "main_ws", other_story.id, name="Harbor Watcher"
        )
        assert same_name_other_story is not None
        with pytest.raises(IntegrityError):
            service.create_character("main_ws", story.id, name="Harbor Watcher")

        detail = service.create_detail(
            "main_ws",
            story.id,
            created.id,
            name="禁忌话题",
            content="不愿谈起灯塔失火。",
            tags=["秘密", " memory ", ""],
            sort_order=20,
        )
        assert detail is not None
        assert detail.tags_json == '["秘密", "memory"]'
        assert service.create_detail(
            "main_ws", other_story.id, created.id, name="Wrong Story"
        ) is None

        updated_detail = service.update_detail(
            "main_ws",
            story.id,
            created.id,
            detail.id,
            name="禁忌话题修订",
            tags=["秘密"],
            sort_order=10,
        )
        assert updated_detail is not None
        assert updated_detail.name == "禁忌话题修订"
        assert updated_detail.version == 2

        updated = service.update_character(
            "main_ws",
            story.id,
            created.id,
            name="Harbor Watcher Revised",
            description="Watchful keeper of the old lighthouse.",
        )
        assert updated is not None
        assert updated.name == "Harbor Watcher Revised"
        assert updated.version == 2
        assert service.update_character(
            "main_ws", other_story.id, created.id, name="Wrong"
        ) is None

        assert service.delete_character("main_ws", story.id, created.id) is True
        assert service.delete_character("main_ws", story.id, created.id) is False
        assert service.list_characters("main_ws", story.id) == []
        assert service.list_characters("main_ws", other_story.id) == [same_name_other_story]
    finally:
        database.close()


def test_character_management_requires_non_empty_names(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)
        with database.atomic():
            workspaces.create("main_ws", "Main", "data/main_ws")
            story = stories.create("main_ws", "Main Story")
        service = CharacterManagementService(database)
        with pytest.raises(ValueError, match="name must not be empty"):
            service.create_character("main_ws", story.id, name="   ")
        character = service.create_character("main_ws", story.id, name="Named")
        assert character is not None
        with pytest.raises(ValueError, match="name must not be empty"):
            service.update_character("main_ws", story.id, character.id, name="\t")
        StoryCharacterRecord.update(name="").where(
            StoryCharacterRecord.id == character.id
        ).execute()
        assert CharacterReadService(database).list_characters("missing") == []
    finally:
        database.close()
