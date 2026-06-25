"""Bootstrap helpers for demo records managed by migrations."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import Story, Workspace, bind_database

DEMO_WORKSPACE_ID = "demo_workspace"
DEMO_WORKSPACE_NAME = "Demo Workspace"
DEMO_WORKSPACE_ROOT_PATH = "data/demo_workspace"
DEMO_STORY_TITLE = "北境森林 Demo"


def get_demo_workspace_and_story(
    database: Database,
) -> tuple[Workspace, Story]:
    """Return the demo workspace and story created by migration 0002."""

    bind_database(database)
    workspace = Workspace.get_by_id(DEMO_WORKSPACE_ID)
    story = Story.get(
        (Story.workspace == DEMO_WORKSPACE_ID)
        & (Story.title == DEMO_STORY_TITLE)
    )
    return workspace, story
