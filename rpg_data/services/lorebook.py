"""Typed persistence services for Story-owned lorebook entries."""

from __future__ import annotations

import json
import logging

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import SessionRecord, StoryLorebookEntryRecord, bind_database
from rpg_data.repositories.story_lorebook_repo import StoryLorebookEntryRepository
from rpg_data.repositories.story_repo import StoryRepository

__all__ = ["LorebookManagementService", "LorebookReadService"]

logger = logging.getLogger("rpg_data.lorebook")


class LorebookReadService:
    """Expose lorebook entries owned by a Session's Story."""

    def __init__(self, database: Database) -> None:
        bind_database(database)

    def list_entries(self, session_id: str) -> list[models.SessionLorebookEntry]:
        session = (
            SessionRecord
            .select()
            .where(SessionRecord.id == session_id)
            .first()
        )
        if session is None:
            return []
        return [
            _to_session_entry(row)
            for row in (
                StoryLorebookEntryRecord
                .select()
                .where(
                    (StoryLorebookEntryRecord.workspace == session.workspace_id)
                    & (StoryLorebookEntryRecord.story == session.story_id)
                )
                .order_by(
                    StoryLorebookEntryRecord.sort_order,
                    StoryLorebookEntryRecord.id,
                )
            )
        ]

    def list_enabled_entries(self, session_id: str) -> list[models.SessionLorebookEntry]:
        return self.list_entries(session_id)

    def get_entry(
        self,
        session_id: str,
        name: str,
    ) -> models.SessionLorebookEntry | None:
        return next(
            (entry for entry in self.list_entries(session_id) if entry.name == name),
            None,
        )


class LorebookManagementService:
    """Manage lorebook entries directly within one Story."""

    def __init__(self, database: Database) -> None:
        bind_database(database)
        self._stories = StoryRepository(database)
        self._entries = StoryLorebookEntryRepository(database)

    def list_entries(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryLorebookEntry] | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        return self._entries.list(workspace_id=workspace_id, story_id=story_id)

    def create_entry(
        self,
        workspace_id: str,
        story_id: int,
        *,
        name: str,
        content: str = "",
        description: str = "",
        tags: list[str] | tuple[str, ...] = (),
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> models.StoryLorebookEntry | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        return self._entries.create(
            workspace_id,
            story_id,
            name.strip(),
            content=content,
            description=description,
            tags_json=_dump_tags(tags),
            sort_order=sort_order,
            metadata_json=_dump_metadata(metadata),
        )

    def update_entry(
        self,
        workspace_id: str,
        story_id: int,
        entry_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        sort_order: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> models.StoryLorebookEntry | None:
        if self._owned_entry(workspace_id, story_id, entry_id) is None:
            return None
        return self._entries.update(
            entry_id,
            name=name.strip() if name is not None else None,
            content=content,
            description=description,
            tags_json=_dump_tags(tags) if tags is not None else None,
            sort_order=sort_order,
            metadata_json=_dump_metadata(metadata) if metadata is not None else None,
        )

    def delete_entry(
        self,
        workspace_id: str,
        story_id: int,
        entry_id: int,
    ) -> bool:
        if self._owned_entry(workspace_id, story_id, entry_id) is None:
            return False
        return self._entries.delete(entry_id)

    def _owned_entry(
        self,
        workspace_id: str,
        story_id: int,
        entry_id: int,
    ) -> models.StoryLorebookEntry | None:
        entry = self._entries.get(entry_id)
        if (
            entry is None
            or entry.workspace_id != workspace_id
            or entry.story_id != story_id
        ):
            return None
        return entry

    def _story_belongs_to_workspace(self, workspace_id: str, story_id: int) -> bool:
        story = self._stories.get(story_id)
        return story is not None and story.workspace_id == workspace_id


def _to_session_entry(row: StoryLorebookEntryRecord) -> models.SessionLorebookEntry:
    return models.SessionLorebookEntry(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        name=str(row.name),
        content=str(row.content or ""),
        description=str(row.description or ""),
        tags=_parse_tags(row.tags_json),
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
