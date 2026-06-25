"""Repository for story-to-character mounts."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import StoryCharacter, bind_database
from rpg_data.repositories._utils import get_or_none, update_timestamp


class StoryCharacterRepository:
    def __init__(self, database: Database) -> None:
        self.database = bind_database(database)

    def create(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        *,
        enabled: bool = True,
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> StoryCharacter:
        return StoryCharacter.create(
            workspace=workspace_id,
            story=story_id,
            character=character_id,
            enabled=enabled,
            sort_order=sort_order,
            metadata_json=metadata_json,
        )

    def list(
        self,
        *,
        workspace_id: str | None = None,
        story_id: int | None = None,
    ) -> list[StoryCharacter]:
        query = StoryCharacter.select()
        if workspace_id is not None:
            query = query.where(StoryCharacter.workspace == workspace_id)
        if story_id is not None:
            query = query.where(StoryCharacter.story == story_id)
        return list(query.order_by(StoryCharacter.story, StoryCharacter.sort_order, StoryCharacter.id))

    def get(self, mount_id: int) -> StoryCharacter | None:
        return get_or_none(StoryCharacter, mount_id)

    def update_timestamp(self, mount_id: int) -> StoryCharacter | None:
        return update_timestamp(StoryCharacter, mount_id)

