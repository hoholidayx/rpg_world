"""Repository for story-to-lorebook-entry mounts."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import StoryLorebookEntry, bind_database
from rpg_data.repositories._utils import get_or_none, update_timestamp


class StoryLorebookEntryRepository:
    def __init__(self, database: Database) -> None:
        self.database = bind_database(database)

    def create(
        self,
        workspace_id: str,
        story_id: int,
        lorebook_entry_id: int,
        *,
        enabled: bool = True,
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> StoryLorebookEntry:
        return StoryLorebookEntry.create(
            workspace=workspace_id,
            story=story_id,
            lorebook_entry=lorebook_entry_id,
            enabled=enabled,
            sort_order=sort_order,
            metadata_json=metadata_json,
        )

    def list(
        self,
        *,
        workspace_id: str | None = None,
        story_id: int | None = None,
    ) -> list[StoryLorebookEntry]:
        query = StoryLorebookEntry.select()
        if workspace_id is not None:
            query = query.where(StoryLorebookEntry.workspace == workspace_id)
        if story_id is not None:
            query = query.where(StoryLorebookEntry.story == story_id)
        return list(
            query.order_by(
                StoryLorebookEntry.story,
                StoryLorebookEntry.sort_order,
                StoryLorebookEntry.id,
            )
        )

    def get(self, mount_id: int) -> StoryLorebookEntry | None:
        return get_or_none(StoryLorebookEntry, mount_id)

    def update_timestamp(self, mount_id: int) -> StoryLorebookEntry | None:
        return update_timestamp(StoryLorebookEntry, mount_id)
