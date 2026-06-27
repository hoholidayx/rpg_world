"""Repository for character detail records."""

from __future__ import annotations

from peewee import Database

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

    def update_timestamp(self, detail_id: int) -> models.CharacterDetail | None:
        row = update_timestamp(CharacterDetailRecord, detail_id)
        return to_character_detail(row) if row is not None else None
