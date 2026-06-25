"""Repository for character detail records."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import CharacterDetail, bind_database
from rpg_data.repositories._utils import get_or_none, update_timestamp


class CharacterDetailRepository:
    def __init__(self, database: Database) -> None:
        self.database = bind_database(database)

    def create(
        self,
        character_id: int,
        name: str,
        *,
        enabled: bool = True,
        content: str = "",
        tags_json: str = "[]",
        sort_order: int = 0,
    ) -> CharacterDetail:
        return CharacterDetail.create(
            character=character_id,
            name=name,
            enabled=enabled,
            content=content,
            tags_json=tags_json,
            sort_order=sort_order,
        )

    def list(self, character_id: int | None = None) -> list[CharacterDetail]:
        query = CharacterDetail.select()
        if character_id is not None:
            query = query.where(CharacterDetail.character == character_id)
        return list(
            query.order_by(
                CharacterDetail.character,
                CharacterDetail.sort_order,
                CharacterDetail.id,
            )
        )

    def get(self, detail_id: int) -> CharacterDetail | None:
        return get_or_none(CharacterDetail, detail_id)

    def update_timestamp(self, detail_id: int) -> CharacterDetail | None:
        return update_timestamp(CharacterDetail, detail_id)

