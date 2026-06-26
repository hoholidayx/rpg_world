"""Repository for story records."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import StoryRecord, bind_database
from rpg_data.repositories._utils import get_or_none, to_story, update_timestamp


class StoryRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        title: str,
        *,
        summary: str = "",
        description: str = "",
        metadata_json: str = "{}",
    ) -> models.Story:
        return to_story(StoryRecord.create(
            workspace=workspace_id,
            title=title,
            summary=summary,
            description=description,
            metadata_json=metadata_json,
        ))

    def list(self, workspace_id: str | None = None) -> list[models.Story]:
        query = StoryRecord.select()
        if workspace_id is not None:
            query = query.where(StoryRecord.workspace == workspace_id)
        return [to_story(row) for row in query.order_by(StoryRecord.created_at, StoryRecord.id)]

    def get(self, story_id: int) -> models.Story | None:
        row = get_or_none(StoryRecord, story_id)
        return to_story(row) if row is not None else None

    def update_timestamp(self, story_id: int) -> models.Story | None:
        row = update_timestamp(StoryRecord, story_id)
        return to_story(row) if row is not None else None
