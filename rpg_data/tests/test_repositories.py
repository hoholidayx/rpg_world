from __future__ import annotations

from pathlib import Path

from peewee import SqliteDatabase

from rpg_data import db
from rpg_data import models
from rpg_data.migrations.runner import run_migrations
from rpg_data.repositories.records import StoryRecord
from rpg_data.repositories.character_detail_repo import CharacterDetailRepository
from rpg_data.repositories.character_repo import CharacterRepository
from rpg_data.repositories.lorebook_repo import LorebookEntryRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_character_repo import StoryCharacterRepository
from rpg_data.repositories.story_lorebook_repo import StoryLorebookEntryRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository

DEMO_WORKSPACE_ID = "demo_workspace"
DEMO_WORKSPACE_ROOT_PATH = "data/demo_workspace"
DEMO_STORY_TITLE = "北境森林 Demo"


def _migrated_database(tmp_path: Path) -> SqliteDatabase:
    db_path = tmp_path / "repositories.sqlite3"
    conn = db.connect(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()

    database = db.bind_peewee_database(db.make_peewee_database(db_path))
    database.connect()
    return database


def _get_demo_workspace_and_story(
    database: SqliteDatabase,
) -> tuple[models.Workspace, models.Story]:
    workspace = WorkspaceRepository(database).get(DEMO_WORKSPACE_ID)
    story = next(
        (
            candidate
            for candidate in StoryRepository(database).list(DEMO_WORKSPACE_ID)
            if candidate.title == DEMO_STORY_TITLE
        ),
        None,
    )
    if workspace is None or story is None:
        raise AssertionError("demo workspace or story is missing")
    return workspace, story


def test_demo_migration_records_can_be_read_by_repositories(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        workspace, story = _get_demo_workspace_and_story(database)
        workspace_again, story_again = _get_demo_workspace_and_story(database)

        assert isinstance(workspace, models.Workspace)
        assert isinstance(story, models.Story)
        assert workspace.id == DEMO_WORKSPACE_ID
        assert workspace.root_path == DEMO_WORKSPACE_ROOT_PATH
        assert story.title == DEMO_STORY_TITLE
        assert workspace_again.id == workspace.id
        assert story_again.id == story.id
        assert (
            StoryRecord.select()
            .where(
                (StoryRecord.workspace == DEMO_WORKSPACE_ID)
                & (StoryRecord.title == DEMO_STORY_TITLE)
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
        rpg_workspaces = WorkspaceRepository(database)
        rpg_stories = StoryRepository(database)
        rpg_sessions = SessionRepository(database)

        with database.atomic():
            workspace = rpg_workspaces.create(
                "campaign",
                "Campaign",
                "data/campaign",
                description="Playtest workspace",
            )
            first_story = rpg_stories.create("campaign", "北境森林")
            second_story = rpg_stories.create("campaign", "学院旧梦")
            forest_main = rpg_sessions.create(
                "campaign",
                first_story.id,
                session_id="s_forestmain",
                title="Forest Main",
            )
            forest_side = rpg_sessions.create(
                "campaign",
                first_story.id,
                session_id="s_forestside",
                title="Forest Side",
                description="Side route",
            )
            academy_main = rpg_sessions.create(
                "campaign",
                second_story.id,
                session_id="s_academymain",
                title="Academy Main",
            )
            generated = rpg_sessions.create(
                "campaign",
                second_story.id,
                title="Generated Main",
            )

        assert isinstance(workspace, models.Workspace)
        assert isinstance(first_story, models.Story)
        assert rpg_workspaces.get("campaign").name == "Campaign"
        assert workspace.root_path == "data/campaign"
        assert [row.title for row in rpg_stories.list("campaign")] == ["北境森林", "学院旧梦"]

        workspace_sessions = rpg_sessions.list(workspace_id="campaign")
        first_story_sessions = rpg_sessions.list(story_id=first_story.id)
        filtered_sessions = rpg_sessions.list(
            workspace_id="campaign",
            story_id=first_story.id,
        )

        assert {row.id for row in workspace_sessions} == {
            forest_main.id,
            forest_side.id,
            academy_main.id,
            generated.id,
        }
        assert [row.id for row in first_story_sessions] == [
            forest_main.id,
            forest_side.id,
        ]
        assert {row.id for row in filtered_sessions} == {
            forest_main.id,
            forest_side.id,
        }
        assert rpg_sessions.get(forest_main.id).title == "Forest Main"
        assert rpg_sessions.get(forest_side.id).description == "Side route"
        assert rpg_sessions.get(academy_main.id).title == "Academy Main"
        assert generated.id.startswith("s_")
        assert len(generated.id) == 12
        assert generated.id[2:].isalnum()
        assert generated.id[2:].islower()

        touched = rpg_sessions.update_timestamp(workspace_sessions[0].id)
        assert isinstance(touched, models.Session)
        assert touched.id == workspace_sessions[0].id
    finally:
        database.close()


def test_character_lorebook_and_mount_repositories(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    try:
        rpg_stories = StoryRepository(database)
        rpg_characters = CharacterRepository(database)
        rpg_character_details = CharacterDetailRepository(database)
        rpg_lorebook_entries = LorebookEntryRepository(database)
        rpg_story_characters = StoryCharacterRepository(database)
        rpg_story_lorebook_entries = StoryLorebookEntryRepository(database)
        rpg_workspaces = WorkspaceRepository(database)

        with database.atomic():
            rpg_workspaces.create("repo_mounts", "Repo Mounts", "data/repo_mounts")
            story = rpg_stories.create("repo_mounts", "北境森林")
            character = rpg_characters.create(
                "repo_mounts",
                "Alice",
                personality="curious",
                content="A young wizard.",
            )
            detail = rpg_character_details.create(
                character.id,
                "外貌",
                content="银白色长发。",
                tags_json='["外观"]',
            )
            lorebook = rpg_lorebook_entries.create(
                "repo_mounts",
                "World History",
                content="Forged from ashes.",
                tags_json='["history"]',
            )
            character_mount = rpg_story_characters.create(
                "repo_mounts",
                story.id,
                character.id,
            )
            lorebook_mount = rpg_story_lorebook_entries.create(
                "repo_mounts",
                story.id,
                lorebook.id,
            )

        assert isinstance(character, models.Character)
        assert isinstance(detail, models.CharacterDetail)
        assert isinstance(lorebook, models.LorebookEntry)
        assert isinstance(character_mount, models.StoryCharacter)
        assert isinstance(lorebook_mount, models.StoryLorebookEntry)
        assert rpg_characters.get(character.id).name == "Alice"
        assert rpg_character_details.list(character.id)[0].id == detail.id
        assert rpg_lorebook_entries.get(lorebook.id).name == "World History"
        assert rpg_story_characters.list(story_id=story.id)[0].id == character_mount.id
        assert (
            rpg_story_lorebook_entries.list(story_id=story.id)[0].id
            == lorebook_mount.id
        )
        touched_character_mount = rpg_story_characters.update_timestamp(character_mount.id)
        touched_lorebook_mount = rpg_story_lorebook_entries.update_timestamp(lorebook_mount.id)

        assert touched_character_mount.id == character_mount.id
        assert touched_lorebook_mount.id == lorebook_mount.id
    finally:
        database.close()
