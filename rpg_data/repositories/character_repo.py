"""Repository for character records."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import Character, bind_database
from rpg_data.repositories._utils import get_or_none, update_timestamp


class CharacterRepository:
    def __init__(self, database: Database) -> None:
        self.database = bind_database(database)

    def create(
        self,
        workspace_id: str,
        name: str,
        *,
        personality: str = "",
        content: str = "",
        metadata_json: str = "{}",
    ) -> Character:
        return Character.create(
            workspace=workspace_id,
            name=name,
            personality=personality,
            content=content,
            metadata_json=metadata_json,
        )

    def list(self, workspace_id: str | None = None) -> list[Character]:
        query = Character.select()
        if workspace_id is not None:
            query = query.where(Character.workspace == workspace_id)
        return list(query.order_by(Character.created_at, Character.id))

    def get(self, character_id: int) -> Character | None:
        return get_or_none(Character, character_id)

    def update_timestamp(self, character_id: int) -> Character | None:
        return update_timestamp(Character, character_id)

