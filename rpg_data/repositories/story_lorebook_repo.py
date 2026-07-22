"""Peewee persistence for Story-owned lorebook entries."""

from __future__ import annotations

from peewee import Database, SQL

from rpg_data import models
from rpg_data.repositories._utils import get_or_none, to_story_lorebook_entry
from rpg_data.repositories.records import StoryLorebookEntryRecord, bind_database


class StoryLorebookEntryRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        story_id: int,
        name: str,
        *,
        content: str = "",
        description: str = "",
        tags_json: str = "[]",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StoryLorebookEntry:
        row = StoryLorebookEntryRecord.create(
            workspace=workspace_id,
            story=story_id,
            name=name,
            content=content,
            description=description,
            tags_json=tags_json,
            sort_order=sort_order,
            metadata_json=metadata_json,
        )
        stored = get_or_none(StoryLorebookEntryRecord, int(row.id))
        if stored is None:
            raise RuntimeError(f"created Story lorebook entry disappeared: {row.id}")
        return to_story_lorebook_entry(stored)

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

    def get(self, entry_id: int) -> models.StoryLorebookEntry | None:
        row = get_or_none(StoryLorebookEntryRecord, entry_id)
        return to_story_lorebook_entry(row) if row is not None else None

    def update(
        self,
        entry_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
        tags_json: str | None = None,
        sort_order: int | None = None,
        metadata_json: str | None = None,
    ) -> models.StoryLorebookEntry | None:
        fields: dict[object, object] = {
            StoryLorebookEntryRecord.updated_at: SQL("CURRENT_TIMESTAMP"),
            StoryLorebookEntryRecord.version: StoryLorebookEntryRecord.version + 1,
        }
        if name is not None:
            fields[StoryLorebookEntryRecord.name] = name
        if content is not None:
            fields[StoryLorebookEntryRecord.content] = content
        if description is not None:
            fields[StoryLorebookEntryRecord.description] = description
        if tags_json is not None:
            fields[StoryLorebookEntryRecord.tags_json] = tags_json
        if sort_order is not None:
            fields[StoryLorebookEntryRecord.sort_order] = sort_order
        if metadata_json is not None:
            fields[StoryLorebookEntryRecord.metadata_json] = metadata_json
        updated = (
            StoryLorebookEntryRecord
            .update(fields)
            .where(StoryLorebookEntryRecord.id == entry_id)
            .execute()
        )
        return self.get(entry_id) if updated else None

    def delete(self, entry_id: int) -> bool:
        return bool(
            StoryLorebookEntryRecord
            .delete()
            .where(StoryLorebookEntryRecord.id == entry_id)
            .execute()
        )
