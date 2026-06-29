"""Repository for character records."""

from __future__ import annotations

from peewee import Database, SQL

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

    def update(
        self,
        character_id: int,
        *,
        name: str | None = None,
        personality: str | None = None,
        content: str | None = None,
        metadata_json: str | None = None,
    ) -> models.Character | None:
        fields: dict[object, object] = {
            CharacterRecord.updated_at: SQL("CURRENT_TIMESTAMP"),
            CharacterRecord.version: CharacterRecord.version + 1,
        }
        if name is not None:
            fields[CharacterRecord.name] = name
        if personality is not None:
            fields[CharacterRecord.personality] = personality
        if content is not None:
            fields[CharacterRecord.content] = content
        if metadata_json is not None:
            fields[CharacterRecord.metadata_json] = metadata_json

        updated = (
            CharacterRecord
            .update(fields)
            .where(CharacterRecord.id == character_id)
            .execute()
        )
        if not updated:
            return None
        return self.get(character_id)

    def update_timestamp(self, character_id: int) -> models.Character | None:
        row = update_timestamp(CharacterRecord, character_id)
        return to_character(row) if row is not None else None

    def delete(self, character_id: int) -> bool:
        return bool(
            CharacterRecord
            .delete()
            .where(CharacterRecord.id == character_id)
            .execute()
        )
