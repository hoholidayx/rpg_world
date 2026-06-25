"""Bootstrap helpers for initial data records."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import Story, Workspace, bind_database

DEFAULT_WORKSPACE_ID = "default"
DEFAULT_WORKSPACE_NAME = "Default"
DEFAULT_WORKSPACE_ROOT_PATH = "data/default_workspace"
DEFAULT_STORY_TITLE = "默认故事"


def ensure_default_workspace_and_story(
    database: Database,
) -> tuple[Workspace, Story]:
    """Ensure the default workspace and story exist, then return both records."""

    bind_database(database)
    workspace, _ = Workspace.get_or_create(
        id=DEFAULT_WORKSPACE_ID,
        defaults={
            "name": DEFAULT_WORKSPACE_NAME,
            "root_path": DEFAULT_WORKSPACE_ROOT_PATH,
            "description": "Default workspace under the data/default_workspace directory",
        },
    )
    story, _ = Story.get_or_create(
        workspace=workspace.id,
        title=DEFAULT_STORY_TITLE,
    )
    return workspace, story
