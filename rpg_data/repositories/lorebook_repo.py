"""Repository for lorebook entry records."""

from __future__ import annotations

from peewee import Database

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

    def update_timestamp(self, entry_id: int) -> models.LorebookEntry | None:
        row = update_timestamp(LorebookEntryRecord, entry_id)
        return to_lorebook_entry(row) if row is not None else None
