"""Typed persistence services for Story-owned character cards."""

from __future__ import annotations

import json
import logging

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import (
    SessionRecord,
    StoryCharacterDetailRecord,
    StoryCharacterRecord,
    bind_database,
)
from rpg_data.repositories.story_character_repo import StoryCharacterRepository
from rpg_data.repositories.story_repo import StoryRepository

__all__ = ["CharacterManagementService", "CharacterReadService"]

logger = logging.getLogger("rpg_data.character")


class CharacterReadService:
    """Expose character cards owned by a Session's Story."""

    def __init__(self, database: Database) -> None:
        bind_database(database)

    def list_characters(self, session_id: str) -> list[models.SessionCharacter]:
        session = (
            SessionRecord
            .select()
            .where(SessionRecord.id == session_id)
            .first()
        )
        if session is None:
            logger.debug("session not found while reading characters: %s", session_id)
            return []

        rows = list(
            StoryCharacterRecord
            .select()
            .where(
                (StoryCharacterRecord.workspace == session.workspace_id)
                & (StoryCharacterRecord.story == session.story_id)
            )
            .order_by(StoryCharacterRecord.sort_order, StoryCharacterRecord.id)
        )
        detail_map = _load_details([int(row.id) for row in rows])
        result = [
            _to_session_character(row, detail_map.get(int(row.id), ()))
            for row in rows
        ]
        logger.debug(
            "listed characters session_id=%s story_id=%s count=%s",
            session_id,
            session.story_id,
            len(result),
        )
        return result

    def get_character(
        self,
        session_id: str,
        name: str,
    ) -> models.SessionCharacter | None:
        return next(
            (
                character
                for character in self.list_characters(session_id)
                if character.name == name
            ),
            None,
        )


class CharacterManagementService:
    """Manage character cards directly within one Story."""

    def __init__(self, database: Database) -> None:
        bind_database(database)
        self._stories = StoryRepository(database)
        self._characters = StoryCharacterRepository(database)

    def list_characters(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryCharacter] | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        return self._characters.list(workspace_id=workspace_id, story_id=story_id)

    def create_character(
        self,
        workspace_id: str,
        story_id: int,
        *,
        name: str,
        description: str = "",
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> models.StoryCharacter | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        character = self._characters.create(
            workspace_id,
            story_id,
            _required_character_name(name),
            description=description,
            sort_order=sort_order,
            metadata_json=_dump_metadata(metadata),
        )
        logger.info(
            "created Story character workspace_id=%s story_id=%s character_id=%s",
            workspace_id,
            story_id,
            character.id,
        )
        return character

    def update_character(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> models.StoryCharacter | None:
        character = self._owned_character(workspace_id, story_id, character_id)
        if character is None:
            return None
        return self._characters.update(
            character_id,
            name=_required_character_name(name) if name is not None else None,
            description=description,
            sort_order=sort_order,
            metadata_json=_dump_metadata(metadata) if metadata is not None else None,
        )

    def delete_character(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
    ) -> bool:
        if self._owned_character(workspace_id, story_id, character_id) is None:
            return False
        return self._characters.delete(character_id)

    def list_details(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
    ) -> list[models.CharacterDetail] | None:
        if self._owned_character(workspace_id, story_id, character_id) is None:
            return None
        return self._characters.list_details(character_id)

    def create_detail(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        *,
        name: str,
        content: str = "",
        tags: list[str] | tuple[str, ...] = (),
        sort_order: int = 0,
    ) -> models.CharacterDetail | None:
        if self._owned_character(workspace_id, story_id, character_id) is None:
            return None
        return self._characters.create_detail(
            character_id,
            name.strip(),
            content=content,
            tags_json=_dump_tags(tags),
            sort_order=sort_order,
        )

    def update_detail(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        detail_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        sort_order: int | None = None,
    ) -> models.CharacterDetail | None:
        detail = self._owned_detail(
            workspace_id,
            story_id,
            character_id,
            detail_id,
        )
        if detail is None:
            return None
        return self._characters.update_detail(
            detail_id,
            name=name.strip() if name is not None else None,
            content=content,
            tags_json=_dump_tags(tags) if tags is not None else None,
            sort_order=sort_order,
        )

    def delete_detail(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        detail_id: int,
    ) -> bool:
        if self._owned_detail(
            workspace_id,
            story_id,
            character_id,
            detail_id,
        ) is None:
            return False
        return self._characters.delete_detail(detail_id)

    def _owned_character(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
    ) -> models.StoryCharacter | None:
        character = self._characters.get(character_id)
        if (
            character is None
            or character.workspace_id != workspace_id
            or character.story_id != story_id
        ):
            return None
        return character

    def _owned_detail(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        detail_id: int,
    ) -> models.CharacterDetail | None:
        if self._owned_character(workspace_id, story_id, character_id) is None:
            return None
        detail = self._characters.get_detail(detail_id)
        if detail is None or detail.story_character_id != character_id:
            return None
        return detail

    def _story_belongs_to_workspace(self, workspace_id: str, story_id: int) -> bool:
        story = self._stories.get(story_id)
        return story is not None and story.workspace_id == workspace_id


def _load_details(
    character_ids: list[int],
) -> dict[int, tuple[models.SessionCharacterDetail, ...]]:
    if not character_ids:
        return {}
    detail_map: dict[int, list[models.SessionCharacterDetail]] = {
        character_id: [] for character_id in character_ids
    }
    rows = (
        StoryCharacterDetailRecord
        .select()
        .where(StoryCharacterDetailRecord.story_character.in_(character_ids))
        .order_by(
            StoryCharacterDetailRecord.story_character,
            StoryCharacterDetailRecord.sort_order,
            StoryCharacterDetailRecord.id,
        )
    )
    for row in rows:
        detail_map[int(row.story_character_id)].append(
            models.SessionCharacterDetail(
                id=int(row.id),
                story_character_id=int(row.story_character_id),
                name=str(row.name),
                content=str(row.content or ""),
                tags=_parse_tags(row.tags_json),
                sort_order=int(row.sort_order),
            )
        )
    return {key: tuple(value) for key, value in detail_map.items()}


def _to_session_character(
    row: StoryCharacterRecord,
    details: tuple[models.SessionCharacterDetail, ...],
) -> models.SessionCharacter:
    return models.SessionCharacter(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        name=str(row.name),
        description=str(row.description or ""),
        details=details,
        sort_order=int(row.sort_order),
    )


def _parse_tags(raw: str | None) -> tuple[str, ...]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return ()
    return tuple(item for item in value if isinstance(item, str)) if isinstance(value, list) else ()


def _dump_tags(tags: list[str] | tuple[str, ...]) -> str:
    return json.dumps(
        [str(tag).strip() for tag in tags if str(tag).strip()],
        ensure_ascii=False,
    )


def _dump_metadata(metadata: dict[str, object] | None) -> str:
    return json.dumps(metadata or {}, ensure_ascii=False)


def _required_character_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Character name must not be empty")
    return value.strip()
