"""Peewee persistence for Story-owned character cards."""

from __future__ import annotations

from peewee import Database, SQL

from rpg_data import models
from rpg_data.repositories._utils import (
    get_or_none,
    to_character_detail,
    to_story_character,
)
from rpg_data.repositories.records import (
    StoryCharacterDetailRecord,
    StoryCharacterRecord,
    bind_database,
)


class StoryCharacterRepository:
    """Internal repository for character cards and their nested details."""

    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        story_id: int,
        name: str,
        *,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StoryCharacter:
        row = StoryCharacterRecord.create(
            workspace=workspace_id,
            story=story_id,
            name=name,
            description=description,
            sort_order=sort_order,
            metadata_json=metadata_json,
        )
        stored = get_or_none(StoryCharacterRecord, int(row.id))
        if stored is None:
            raise RuntimeError(f"created Story character disappeared: {row.id}")
        return to_story_character(stored)

    def list(
        self,
        *,
        workspace_id: str | None = None,
        story_id: int | None = None,
    ) -> list[models.StoryCharacter]:
        query = StoryCharacterRecord.select()
        if workspace_id is not None:
            query = query.where(StoryCharacterRecord.workspace == workspace_id)
        if story_id is not None:
            query = query.where(StoryCharacterRecord.story == story_id)
        return [
            to_story_character(row)
            for row in query.order_by(
                StoryCharacterRecord.story,
                StoryCharacterRecord.sort_order,
                StoryCharacterRecord.id,
            )
        ]

    def get(self, character_id: int) -> models.StoryCharacter | None:
        row = get_or_none(StoryCharacterRecord, character_id)
        return to_story_character(row) if row is not None else None

    def update(
        self,
        character_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
        metadata_json: str | None = None,
    ) -> models.StoryCharacter | None:
        fields: dict[object, object] = {
            StoryCharacterRecord.updated_at: SQL("CURRENT_TIMESTAMP"),
            StoryCharacterRecord.version: StoryCharacterRecord.version + 1,
        }
        if name is not None:
            fields[StoryCharacterRecord.name] = name
        if description is not None:
            fields[StoryCharacterRecord.description] = description
        if sort_order is not None:
            fields[StoryCharacterRecord.sort_order] = sort_order
        if metadata_json is not None:
            fields[StoryCharacterRecord.metadata_json] = metadata_json
        updated = (
            StoryCharacterRecord
            .update(fields)
            .where(StoryCharacterRecord.id == character_id)
            .execute()
        )
        return self.get(character_id) if updated else None

    def delete(self, character_id: int) -> bool:
        return bool(
            StoryCharacterRecord
            .delete()
            .where(StoryCharacterRecord.id == character_id)
            .execute()
        )

    def list_details(self, character_id: int) -> list[models.CharacterDetail]:
        return [
            to_character_detail(row)
            for row in (
                StoryCharacterDetailRecord
                .select()
                .where(StoryCharacterDetailRecord.story_character == character_id)
                .order_by(
                    StoryCharacterDetailRecord.sort_order,
                    StoryCharacterDetailRecord.id,
                )
            )
        ]

    def get_detail(self, detail_id: int) -> models.CharacterDetail | None:
        row = get_or_none(StoryCharacterDetailRecord, detail_id)
        return to_character_detail(row) if row is not None else None

    def create_detail(
        self,
        character_id: int,
        name: str,
        *,
        content: str = "",
        tags_json: str = "[]",
        sort_order: int = 0,
    ) -> models.CharacterDetail:
        row = StoryCharacterDetailRecord.create(
            story_character=character_id,
            name=name,
            content=content,
            tags_json=tags_json,
            sort_order=sort_order,
        )
        stored = get_or_none(StoryCharacterDetailRecord, int(row.id))
        if stored is None:
            raise RuntimeError(f"created character detail disappeared: {row.id}")
        return to_character_detail(stored)

    def update_detail(
        self,
        detail_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        tags_json: str | None = None,
        sort_order: int | None = None,
    ) -> models.CharacterDetail | None:
        fields: dict[object, object] = {
            StoryCharacterDetailRecord.updated_at: SQL("CURRENT_TIMESTAMP"),
            StoryCharacterDetailRecord.version: StoryCharacterDetailRecord.version + 1,
        }
        if name is not None:
            fields[StoryCharacterDetailRecord.name] = name
        if content is not None:
            fields[StoryCharacterDetailRecord.content] = content
        if tags_json is not None:
            fields[StoryCharacterDetailRecord.tags_json] = tags_json
        if sort_order is not None:
            fields[StoryCharacterDetailRecord.sort_order] = sort_order
        updated = (
            StoryCharacterDetailRecord
            .update(fields)
            .where(StoryCharacterDetailRecord.id == detail_id)
            .execute()
        )
        return self.get_detail(detail_id) if updated else None

    def delete_detail(self, detail_id: int) -> bool:
        return bool(
            StoryCharacterDetailRecord
            .delete()
            .where(StoryCharacterDetailRecord.id == detail_id)
            .execute()
        )
