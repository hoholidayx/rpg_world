"""Read service for session-scoped character cards."""

from __future__ import annotations

import json
import logging

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import (
    CharacterDetailRecord,
    CharacterRecord,
    SessionRecord,
    StoryCharacterRecord,
    bind_database,
)

__all__ = ["CharacterReadService"]

logger = logging.getLogger("rpg_data.character")


class CharacterReadService:
    """Expose character cards mounted to a session's story."""

    def __init__(self, database: Database) -> None:
        bind_database(database)

    def list_characters(self, session_id: str) -> list[models.SessionCharacter]:
        """Return character cards mounted to ``session_id``'s story."""

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
            .select(StoryCharacterRecord, CharacterRecord)
            .join(CharacterRecord)
            .where(
                (StoryCharacterRecord.workspace == session.workspace_id)
                & (StoryCharacterRecord.story == session.story_id)
            )
            .order_by(
                StoryCharacterRecord.sort_order,
                StoryCharacterRecord.id,
            )
        )
        detail_map = _load_details([int(row.character_id) for row in rows])
        result = [
            _to_session_character(row, detail_map.get(int(row.character_id), ()))
            for row in rows
        ]
        logger.debug(
            "listed characters session_id=%s workspace_id=%s story_id=%s count=%s names=%s",
            session_id,
            session.workspace_id,
            session.story_id,
            len(result),
            [character.name for character in result],
        )
        return result

    def get_character(
        self,
        session_id: str,
        name: str,
    ) -> models.SessionCharacter | None:
        """Return one mounted character card by name."""

        for character in self.list_characters(session_id):
            if character.name == name:
                logger.debug("loaded character session_id=%s name=%s character_id=%s", session_id, name, character.id)
                return character
        logger.debug("character not found session_id=%s name=%s", session_id, name)
        return None


def _load_details(character_ids: list[int]) -> dict[int, tuple[models.SessionCharacterDetail, ...]]:
    if not character_ids:
        return {}

    detail_map: dict[int, list[models.SessionCharacterDetail]] = {
        character_id: []
        for character_id in character_ids
    }
    rows = (
        CharacterDetailRecord
        .select()
        .where(CharacterDetailRecord.character.in_(character_ids))
        .order_by(
            CharacterDetailRecord.character,
            CharacterDetailRecord.sort_order,
            CharacterDetailRecord.id,
        )
    )
    for row in rows:
        detail_map.setdefault(int(row.character_id), []).append(_to_session_character_detail(row))
    return {
        character_id: tuple(details)
        for character_id, details in detail_map.items()
    }


def _to_session_character(
    mount: StoryCharacterRecord,
    details: tuple[models.SessionCharacterDetail, ...],
) -> models.SessionCharacter:
    character = mount.character
    return models.SessionCharacter(
        id=int(character.id),
        mount_id=int(mount.id),
        workspace_id=str(mount.workspace_id),
        story_id=int(mount.story_id),
        name=str(character.name),
        personality=str(character.personality or ""),
        content=str(character.content or ""),
        details=details,
        sort_order=int(mount.sort_order),
    )


def _to_session_character_detail(
    row: CharacterDetailRecord,
) -> models.SessionCharacterDetail:
    return models.SessionCharacterDetail(
        id=int(row.id),
        character_id=int(row.character_id),
        name=str(row.name),
        content=str(row.content or ""),
        tags=_parse_tags(row.tags_json),
        sort_order=int(row.sort_order),
    )


def _parse_tags(raw: str | None) -> tuple[str, ...]:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(item for item in data if isinstance(item, str))
