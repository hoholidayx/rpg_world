"""Repository for character records."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import CharacterRecord, bind_database
from rpg_data.repositories._utils import get_or_none, to_character, update_timestamp


class CharacterRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        name: str,
        *,
        personality: str = "",
        content: str = "",
        metadata_json: str = "{}",
    ) -> models.Character:
        return to_character(CharacterRecord.create(
            workspace=workspace_id,
            name=name,
            personality=personality,
            content=content,
            metadata_json=metadata_json,
        ))

    def list(self, workspace_id: str | None = None) -> list[models.Character]:
        query = CharacterRecord.select()
        if workspace_id is not None:
            query = query.where(CharacterRecord.workspace == workspace_id)
        return [
            to_character(row)
            for row in query.order_by(
                CharacterRecord.created_at,
                CharacterRecord.id,
            )
        ]

    def get(self, character_id: int) -> models.Character | None:
        row = get_or_none(CharacterRecord, character_id)
        return to_character(row) if row is not None else None

    def update_timestamp(self, character_id: int) -> models.Character | None:
        row = update_timestamp(CharacterRecord, character_id)
        return to_character(row) if row is not None else None
