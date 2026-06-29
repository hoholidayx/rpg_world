"""Read service for session-scoped character cards."""

from __future__ import annotations

import json
import logging

from peewee import Database

from rpg_data import models
from rpg_data.repositories.character_detail_repo import CharacterDetailRepository
from rpg_data.repositories.character_repo import CharacterRepository
from rpg_data.repositories.records import (
    CharacterDetailRecord,
    CharacterRecord,
    SessionRecord,
    StoryCharacterRecord,
    bind_database,
)
from rpg_data.repositories.story_character_repo import StoryCharacterRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository

__all__ = ["CharacterManagementService", "CharacterReadService"]

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


class CharacterManagementService:
    """Manage workspace character cards, details, and story mounts."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        self._workspaces = WorkspaceRepository(database)
        self._stories = StoryRepository(database)
        self._characters = CharacterRepository(database)
        self._details = CharacterDetailRepository(database)
        self._mounts = StoryCharacterRepository(database)

    def list_characters(self, workspace_id: str) -> list[models.Character] | None:
        if self._workspaces.get(workspace_id) is None:
            return None
        return self._characters.list(workspace_id)

    def create_character(
        self,
        workspace_id: str,
        *,
        name: str,
        personality: str = "",
        content: str = "",
        metadata: dict[str, object] | None = None,
    ) -> models.Character | None:
        if self._workspaces.get(workspace_id) is None:
            return None
        character = self._characters.create(
            workspace_id,
            name.strip(),
            personality=personality,
            content=content,
            metadata_json=_dump_metadata(metadata),
        )
        logger.info("created character workspace_id=%s character_id=%s name=%s", workspace_id, character.id, character.name)
        return character

    def update_character(
        self,
        workspace_id: str,
        character_id: int,
        *,
        name: str | None = None,
        personality: str | None = None,
        content: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> models.Character | None:
        character = self._characters.get(character_id)
        if character is None or character.workspace_id != workspace_id:
            return None
        updated = self._characters.update(
            character_id,
            name=name.strip() if name is not None else None,
            personality=personality,
            content=content,
            metadata_json=_dump_metadata(metadata) if metadata is not None else None,
        )
        if updated is None:
            return None
        logger.info("updated character workspace_id=%s character_id=%s name=%s", workspace_id, character_id, updated.name)
        return updated

    def delete_character(self, workspace_id: str, character_id: int) -> bool:
        character = self._characters.get(character_id)
        if character is None or character.workspace_id != workspace_id:
            return False
        deleted = self._characters.delete(character_id)
        logger.info(
            "deleted character workspace_id=%s character_id=%s deleted=%s",
            workspace_id,
            character_id,
            deleted,
        )
        return deleted

    def list_details(
        self,
        workspace_id: str,
        character_id: int,
    ) -> list[models.CharacterDetail] | None:
        character = self._characters.get(character_id)
        if character is None or character.workspace_id != workspace_id:
            return None
        return self._details.list(character_id)

    def create_detail(
        self,
        workspace_id: str,
        character_id: int,
        *,
        name: str,
        content: str = "",
        tags: list[str] | tuple[str, ...] = (),
        sort_order: int = 0,
    ) -> models.CharacterDetail | None:
        character = self._characters.get(character_id)
        if character is None or character.workspace_id != workspace_id:
            return None
        detail = self._details.create(
            character_id,
            name.strip(),
            content=content,
            tags_json=_dump_tags(tags),
            sort_order=sort_order,
        )
        logger.info(
            "created character detail workspace_id=%s character_id=%s detail_id=%s name=%s",
            workspace_id,
            character_id,
            detail.id,
            detail.name,
        )
        return detail

    def update_detail(
        self,
        workspace_id: str,
        character_id: int,
        detail_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        sort_order: int | None = None,
    ) -> models.CharacterDetail | None:
        character = self._characters.get(character_id)
        detail = self._details.get(detail_id)
        if (
            character is None
            or character.workspace_id != workspace_id
            or detail is None
            or detail.character_id != character_id
        ):
            return None
        updated = self._details.update(
            detail_id,
            name=name.strip() if name is not None else None,
            content=content,
            tags_json=_dump_tags(tags) if tags is not None else None,
            sort_order=sort_order,
        )
        if updated is None:
            return None
        logger.info(
            "updated character detail workspace_id=%s character_id=%s detail_id=%s name=%s",
            workspace_id,
            character_id,
            detail_id,
            updated.name,
        )
        return updated

    def delete_detail(
        self,
        workspace_id: str,
        character_id: int,
        detail_id: int,
    ) -> bool:
        character = self._characters.get(character_id)
        detail = self._details.get(detail_id)
        if (
            character is None
            or character.workspace_id != workspace_id
            or detail is None
            or detail.character_id != character_id
        ):
            return False
        deleted = self._details.delete(detail_id)
        logger.info(
            "deleted character detail workspace_id=%s character_id=%s detail_id=%s deleted=%s",
            workspace_id,
            character_id,
            detail_id,
            deleted,
        )
        return deleted

    def list_story_characters(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryCharacterDetail] | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        rows = (
            StoryCharacterRecord
            .select(StoryCharacterRecord, CharacterRecord)
            .join(CharacterRecord)
            .where(
                (StoryCharacterRecord.workspace == workspace_id)
                & (StoryCharacterRecord.story == story_id)
            )
            .order_by(StoryCharacterRecord.sort_order, StoryCharacterRecord.id)
        )
        return [_to_story_character_detail(row) for row in rows]

    def mount_character(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
    ) -> models.StoryCharacterDetail | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        character = self._characters.get(character_id)
        if character is None or character.workspace_id != workspace_id:
            return None
        with self._database.atomic():
            mount = self._mounts.mount(workspace_id, story_id, character_id)
        logger.info(
            "mounted character workspace_id=%s story_id=%s character_id=%s mount_id=%s",
            workspace_id,
            story_id,
            character_id,
            mount.id,
        )
        return _to_story_character_detail(_get_mount_record(mount.id))

    def unmount_character(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        mount = self._mounts.get(mount_id)
        if mount is None or mount.workspace_id != workspace_id or mount.story_id != story_id:
            return False
        deleted = self._mounts.delete(mount_id)
        logger.info(
            "unmounted character workspace_id=%s story_id=%s mount_id=%s deleted=%s",
            workspace_id,
            story_id,
            mount_id,
            deleted,
        )
        return deleted

    def _story_belongs_to_workspace(self, workspace_id: str, story_id: int) -> bool:
        story = self._stories.get(story_id)
        return story is not None and story.workspace_id == workspace_id


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


def _to_story_character_detail(mount_row: StoryCharacterRecord) -> models.StoryCharacterDetail:
    character = mount_row.character
    mount = models.StoryCharacter(
        id=int(mount_row.id),
        workspace_id=str(mount_row.workspace_id),
        story_id=int(mount_row.story_id),
        character_id=int(mount_row.character_id),
        sort_order=int(mount_row.sort_order),
        metadata_json=str(mount_row.metadata_json or "{}"),
        version=int(mount_row.version),
        created_at=str(mount_row.created_at),
        updated_at=str(mount_row.updated_at),
    )
    return models.StoryCharacterDetail(
        mount=mount,
        character=models.Character(
            id=int(character.id),
            workspace_id=str(character.workspace_id),
            name=str(character.name),
            personality=str(character.personality or ""),
            content=str(character.content or ""),
            metadata_json=str(character.metadata_json or "{}"),
            version=int(character.version),
            created_at=str(character.created_at),
            updated_at=str(character.updated_at),
        ),
    )


def _get_mount_record(mount_id: int) -> StoryCharacterRecord:
    row = (
        StoryCharacterRecord
        .select(StoryCharacterRecord, CharacterRecord)
        .join(CharacterRecord)
        .where(StoryCharacterRecord.id == mount_id)
        .first()
    )
    if row is None:
        raise LookupError(f"Character mount not found after create: {mount_id}")
    return row


def _parse_tags(raw: str | None) -> tuple[str, ...]:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(item for item in data if isinstance(item, str))


def _dump_tags(tags: list[str] | tuple[str, ...]) -> str:
    cleaned = [str(tag).strip() for tag in tags if str(tag).strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def _dump_metadata(metadata: dict[str, object] | None) -> str:
    return json.dumps(metadata or {}, ensure_ascii=False)
