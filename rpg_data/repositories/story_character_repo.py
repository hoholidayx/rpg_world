"""Repository for story-to-character mounts."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import StoryCharacterRecord, bind_database
from rpg_data.repositories._utils import get_or_none, to_story_character, update_timestamp


class StoryCharacterRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        *,
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StoryCharacter:
        return to_story_character(StoryCharacterRecord.create(
            workspace=workspace_id,
            story=story_id,
            character=character_id,
            sort_order=sort_order,
            metadata_json=metadata_json,
        ))

    def list(
        self,
        *,
        workspace_id: str | None = None,
        story_id: int | None = None,
    ) -> list[models.StoryCharacter]:
        query = StoryCharacterRecord.select()
        if workspace_id is not None:
            query = query.where(StoryCharacterRecord.workspace == workspace_id)
        if story_id is not None:
            query = query.where(StoryCharacterRecord.story == story_id)
        return [
            to_story_character(row)
            for row in query.order_by(
                StoryCharacterRecord.story,
                StoryCharacterRecord.sort_order,
                StoryCharacterRecord.id,
            )
        ]

    def get(self, mount_id: int) -> models.StoryCharacter | None:
        row = get_or_none(StoryCharacterRecord, mount_id)
        return to_story_character(row) if row is not None else None

    def update_timestamp(self, mount_id: int) -> models.StoryCharacter | None:
        row = update_timestamp(StoryCharacterRecord, mount_id)
        return to_story_character(row) if row is not None else None
