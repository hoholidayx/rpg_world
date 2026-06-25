"""Repository for lorebook entry records."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import LorebookEntry, bind_database
from rpg_data.repositories._utils import get_or_none, update_timestamp


class LorebookEntryRepository:
    def __init__(self, database: Database) -> None:
        self.database = bind_database(database)

    def create(
        self,
        workspace_id: str,
        name: str,
        *,
        content: str = "",
        description: str = "",
        tags_json: str = "[]",
        metadata_json: str = "{}",
    ) -> LorebookEntry:
        return LorebookEntry.create(
            workspace=workspace_id,
            name=name,
            content=content,
            description=description,
            tags_json=tags_json,
            metadata_json=metadata_json,
        )

    def list(self, workspace_id: str | None = None) -> list[LorebookEntry]:
        query = LorebookEntry.select()
        if workspace_id is not None:
            query = query.where(LorebookEntry.workspace == workspace_id)
        return list(query.order_by(LorebookEntry.created_at, LorebookEntry.id))

    def get(self, entry_id: int) -> LorebookEntry | None:
        return get_or_none(LorebookEntry, entry_id)

    def update_timestamp(self, entry_id: int) -> LorebookEntry | None:
        return update_timestamp(LorebookEntry, entry_id)

