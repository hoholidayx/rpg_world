"""Repository for story-to-lorebook-entry mounts."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import StoryLorebookEntryRecord, bind_database
from rpg_data.repositories._utils import get_or_none, to_story_lorebook_entry, update_timestamp


class StoryLorebookEntryRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        story_id: int,
        lorebook_entry_id: int,
        *,
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StoryLorebookEntry:
        return to_story_lorebook_entry(StoryLorebookEntryRecord.create(
            workspace=workspace_id,
            story=story_id,
            lorebook_entry=lorebook_entry_id,
            sort_order=sort_order,
            metadata_json=metadata_json,
        ))

    def list(
        self,
        *,
        workspace_id: str | None = None,
        story_id: int | None = None,
    ) -> list[models.StoryLorebookEntry]:
        query = StoryLorebookEntryRecord.select()
        if workspace_id is not None:
            query = query.where(StoryLorebookEntryRecord.workspace == workspace_id)
        if story_id is not None:
            query = query.where(StoryLorebookEntryRecord.story == story_id)
        return [
            to_story_lorebook_entry(row)
            for row in query.order_by(
                StoryLorebookEntryRecord.story,
                StoryLorebookEntryRecord.sort_order,
                StoryLorebookEntryRecord.id,
            )
        ]

    def get(self, mount_id: int) -> models.StoryLorebookEntry | None:
        row = get_or_none(StoryLorebookEntryRecord, mount_id)
        return to_story_lorebook_entry(row) if row is not None else None

    def update_timestamp(self, mount_id: int) -> models.StoryLorebookEntry | None:
        row = update_timestamp(StoryLorebookEntryRecord, mount_id)
        return to_story_lorebook_entry(row) if row is not None else None
