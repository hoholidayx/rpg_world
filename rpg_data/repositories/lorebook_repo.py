"""Repository for lorebook entry records."""

from __future__ import annotations

from peewee import Database, SQL

from rpg_data import models
from rpg_data.repositories.records import LorebookEntryRecord, bind_database
from rpg_data.repositories._utils import get_or_none, to_lorebook_entry, update_timestamp


class LorebookEntryRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        name: str,
        *,
        content: str = "",
        description: str = "",
        tags_json: str = "[]",
        metadata_json: str = "{}",
    ) -> models.LorebookEntry:
        return to_lorebook_entry(LorebookEntryRecord.create(
            workspace=workspace_id,
            name=name,
            content=content,
            description=description,
            tags_json=tags_json,
            metadata_json=metadata_json,
        ))

    def list(self, workspace_id: str | None = None) -> list[models.LorebookEntry]:
        query = LorebookEntryRecord.select()
        if workspace_id is not None:
            query = query.where(LorebookEntryRecord.workspace == workspace_id)
        return [
            to_lorebook_entry(row)
            for row in query.order_by(LorebookEntryRecord.created_at, LorebookEntryRecord.id)
        ]

    def get(self, entry_id: int) -> models.LorebookEntry | None:
        row = get_or_none(LorebookEntryRecord, entry_id)
        return to_lorebook_entry(row) if row is not None else None

    def update(
        self,
        entry_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
        tags_json: str | None = None,
        metadata_json: str | None = None,
    ) -> models.LorebookEntry | None:
        fields: dict[object, object] = {
            LorebookEntryRecord.updated_at: SQL("CURRENT_TIMESTAMP"),
            LorebookEntryRecord.version: LorebookEntryRecord.version + 1,
        }
        if name is not None:
            fields[LorebookEntryRecord.name] = name
        if content is not None:
            fields[LorebookEntryRecord.content] = content
        if description is not None:
            fields[LorebookEntryRecord.description] = description
        if tags_json is not None:
            fields[LorebookEntryRecord.tags_json] = tags_json
        if metadata_json is not None:
            fields[LorebookEntryRecord.metadata_json] = metadata_json

        updated = (
            LorebookEntryRecord
            .update(fields)
            .where(LorebookEntryRecord.id == entry_id)
            .execute()
        )
        if not updated:
            return None
        return self.get(entry_id)

    def update_timestamp(self, entry_id: int) -> models.LorebookEntry | None:
        row = update_timestamp(LorebookEntryRecord, entry_id)
        return to_lorebook_entry(row) if row is not None else None

    def delete(self, entry_id: int) -> bool:
        return bool(
            LorebookEntryRecord
            .delete()
            .where(LorebookEntryRecord.id == entry_id)
            .execute()
        )
