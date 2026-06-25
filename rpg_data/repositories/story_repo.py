"""Repository for story records."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import Story, bind_database
from rpg_data.repositories._utils import get_or_none, update_timestamp


class StoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = bind_database(database)

    def create(
        self,
        workspace_id: str,
        title: str,
        *,
        summary: str = "",
        description: str = "",
        metadata_json: str = "{}",
    ) -> Story:
        return Story.create(
            workspace=workspace_id,
            title=title,
            summary=summary,
            description=description,
            metadata_json=metadata_json,
        )

    def list(self, workspace_id: str | None = None) -> list[Story]:
        query = Story.select()
        if workspace_id is not None:
            query = query.where(Story.workspace == workspace_id)
        return list(query.order_by(Story.created_at, Story.id))

    def get(self, story_id: int) -> Story | None:
        return get_or_none(Story, story_id)

    def update_timestamp(self, story_id: int) -> Story | None:
        return update_timestamp(Story, story_id)

