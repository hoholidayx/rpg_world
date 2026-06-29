"""Repository for character detail records."""

from __future__ import annotations

from peewee import Database, SQL

from rpg_data import models
from rpg_data.repositories.records import CharacterDetailRecord, bind_database
from rpg_data.repositories._utils import get_or_none, to_character_detail, update_timestamp


class CharacterDetailRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        character_id: int,
        name: str,
        *,
        content: str = "",
        tags_json: str = "[]",
        sort_order: int = 0,
    ) -> models.CharacterDetail:
        return to_character_detail(CharacterDetailRecord.create(
            character=character_id,
            name=name,
            content=content,
            tags_json=tags_json,
            sort_order=sort_order,
        ))

    def list(self, character_id: int | None = None) -> list[models.CharacterDetail]:
        query = CharacterDetailRecord.select()
        if character_id is not None:
            query = query.where(CharacterDetailRecord.character == character_id)
        return [
            to_character_detail(row)
            for row in query.order_by(
                CharacterDetailRecord.character,
                CharacterDetailRecord.sort_order,
                CharacterDetailRecord.id,
            )
        ]

    def get(self, detail_id: int) -> models.CharacterDetail | None:
        row = get_or_none(CharacterDetailRecord, detail_id)
        return to_character_detail(row) if row is not None else None

    def update(
        self,
        detail_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        tags_json: str | None = None,
        sort_order: int | None = None,
    ) -> models.CharacterDetail | None:
        fields: dict[object, object] = {
            CharacterDetailRecord.updated_at: SQL("CURRENT_TIMESTAMP"),
            CharacterDetailRecord.version: CharacterDetailRecord.version + 1,
        }
        if name is not None:
            fields[CharacterDetailRecord.name] = name
        if content is not None:
            fields[CharacterDetailRecord.content] = content
        if tags_json is not None:
            fields[CharacterDetailRecord.tags_json] = tags_json
        if sort_order is not None:
            fields[CharacterDetailRecord.sort_order] = sort_order

        updated = (
            CharacterDetailRecord
            .update(fields)
            .where(CharacterDetailRecord.id == detail_id)
            .execute()
        )
        if not updated:
            return None
        return self.get(detail_id)

    def update_timestamp(self, detail_id: int) -> models.CharacterDetail | None:
        row = update_timestamp(CharacterDetailRecord, detail_id)
        return to_character_detail(row) if row is not None else None

    def delete(self, detail_id: int) -> bool:
        return bool(
            CharacterDetailRecord
            .delete()
            .where(CharacterDetailRecord.id == detail_id)
            .execute()
        )
