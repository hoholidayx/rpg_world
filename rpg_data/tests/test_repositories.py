from __future__ import annotations

from pathlib import Path

from peewee import SqliteDatabase

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.orm import Story, bind_database, make_database
from rpg_data.repositories.character_detail_repo import CharacterDetailRepository
from rpg_data.repositories.character_repo import CharacterRepository
from rpg_data.repositories.lorebook_repo import LorebookEntryRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_character_repo import StoryCharacterRepository
from rpg_data.repositories.story_lorebook_repo import StoryLorebookEntryRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services.bootstrap import (
    DEFAULT_STORY_TITLE,
    DEFAULT_WORKSPACE_ID,
    DEFAULT_WORKSPACE_ROOT_PATH,
    ensure_default_workspace_and_story,
)


def _migrated_database(tmp_path: Path) -> SqliteDatabase:
    db_path = tmp_path / "repositories.sqlite3"
    conn = db.connect(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()

    database = make_database(db_path)
    bind_database(database)
    database.connect()
    return database


def test_bootstrap_ensures_default_workspace_and_story(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspace, story = ensure_default_workspace_and_story(database)
        workspace_again, story_again = ensure_default_workspace_and_story(database)

        assert workspace.id == DEFAULT_WORKSPACE_ID
        assert workspace.root_path == DEFAULT_WORKSPACE_ROOT_PATH
        assert story.title == DEFAULT_STORY_TITLE
        assert workspace_again.id == workspace.id
        assert story_again.id == story.id
        assert (
            Story.select()
            .where(
                (Story.workspace == DEFAULT_WORKSPACE_ID)
                & (Story.title == DEFAULT_STORY_TITLE)
            )
            .count()
            == 1
        )
    finally:
        database.close()


def test_repositories_create_workspace_story_session_and_query_sessions(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)
        sessions = SessionRepository(database)

        with database.atomic():
            workspace = workspaces.create(
                "campaign",
                "Campaign",
                "data/campaign",
                description="Playtest workspace",
            )
            first_story = stories.create("campaign", "北境森林")
            second_story = stories.create("campaign", "学院旧梦")
            sessions.create(
                "campaign",
                "forest_main",
                story_id=first_story.id,
                title="Forest Main",
            )
            sessions.create(
                "campaign",
                "forest_side",
                story_id=first_story.id,
                title="Forest Side",
            )
            sessions.create(
                "campaign",
                "academy_main",
                story_id=second_story.id,
                title="Academy Main",
            )

        assert workspaces.get("campaign").name == "Campaign"
        assert workspace.root_path == "data/campaign"
        assert [row.title for row in stories.list("campaign")] == ["北境森林", "学院旧梦"]

        workspace_sessions = sessions.list(workspace_id="campaign")
        first_story_sessions = sessions.list(story_id=first_story.id)
        filtered_sessions = sessions.list(
            workspace_id="campaign",
            story_id=first_story.id,
        )

        assert [row.session_key for row in workspace_sessions] == [
            "forest_main",
            "forest_side",
            "academy_main",
        ]
        assert [row.session_key for row in first_story_sessions] == [
            "forest_main",
            "forest_side",
        ]
        assert [row.session_key for row in filtered_sessions] == [
            "forest_main",
            "forest_side",
        ]

        touched = sessions.update_timestamp(workspace_sessions[0].id)
        assert touched.id == workspace_sessions[0].id
    finally:
        database.close()


def test_character_lorebook_and_mount_repositories(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        stories = StoryRepository(database)
        characters = CharacterRepository(database)
        character_details = CharacterDetailRepository(database)
        lorebook_entries = LorebookEntryRepository(database)
        story_characters = StoryCharacterRepository(database)
        story_lorebook_entries = StoryLorebookEntryRepository(database)

        with database.atomic():
            story = stories.create("default", "北境森林")
            character = characters.create(
                "default",
                "Alice",
                personality="curious",
                content="A young wizard.",
            )
            detail = character_details.create(
                character.id,
                "外貌",
                content="银白色长发。",
                tags_json='["外观"]',
            )
            lorebook = lorebook_entries.create(
                "default",
                "World History",
                content="Forged from ashes.",
                tags_json='["history"]',
            )
            character_mount = story_characters.create(
                "default",
                story.id,
                character.id,
            )
            lorebook_mount = story_lorebook_entries.create(
                "default",
                story.id,
                lorebook.id,
            )

        assert characters.get(character.id).name == "Alice"
        assert character_details.list(character.id)[0].id == detail.id
        assert lorebook_entries.get(lorebook.id).name == "World History"
        assert story_characters.list(story_id=story.id)[0].id == character_mount.id
        assert (
            story_lorebook_entries.list(story_id=story.id)[0].id
            == lorebook_mount.id
        )
        touched_character_mount = story_characters.update_timestamp(character_mount.id)
        touched_lorebook_mount = story_lorebook_entries.update_timestamp(lorebook_mount.id)

        assert touched_character_mount.id == character_mount.id
        assert touched_lorebook_mount.id == lorebook_mount.id
    finally:
        database.close()
