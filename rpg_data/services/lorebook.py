"""Read service for session-scoped lorebook entries."""

from __future__ import annotations

import json
import logging

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import (
    LorebookEntryRecord,
    SessionRecord,
    StoryLorebookEntryRecord,
    bind_database,
)

__all__ = ["LorebookReadService"]

logger = logging.getLogger("rpg_data.lorebook")


class LorebookReadService:
    """Expose lorebook entries mounted to a session's story."""

    def __init__(self, database: Database) -> None:
        bind_database(database)

    def list_entries(
        self,
        session_id: str,
        *,
        enabled_only: bool = False,
    ) -> list[models.SessionLorebookEntry]:
        """Return lorebook entries mounted to ``session_id``'s story."""

        session = (
            SessionRecord
            .select()
            .where(SessionRecord.id == session_id)
            .first()
        )
        if session is None:
            logger.debug("session not found while reading lorebook: %s", session_id)
            return []

        query = (
            StoryLorebookEntryRecord
            .select(StoryLorebookEntryRecord, LorebookEntryRecord)
            .join(LorebookEntryRecord)
            .where(
                (StoryLorebookEntryRecord.workspace == session.workspace_id)
                & (StoryLorebookEntryRecord.story == session.story_id)
            )
        )
        if enabled_only:
            query = query.where(StoryLorebookEntryRecord.enabled == True)  # noqa: E712

        return [
            _to_session_lorebook_entry(row)
            for row in query.order_by(
                StoryLorebookEntryRecord.sort_order,
                StoryLorebookEntryRecord.id,
            )
        ]

    def list_enabled_entries(self, session_id: str) -> list[models.SessionLorebookEntry]:
        """Return enabled lorebook entries mounted to ``session_id``'s story."""

        return self.list_entries(session_id, enabled_only=True)

    def get_entry(
        self,
        session_id: str,
        name: str,
        *,
        enabled_only: bool = False,
    ) -> models.SessionLorebookEntry | None:
        """Return one mounted lorebook entry by name."""

        for entry in self.list_entries(session_id, enabled_only=enabled_only):
            if entry.name == name:
                return entry
        return None


def _to_session_lorebook_entry(
    mount: StoryLorebookEntryRecord,
) -> models.SessionLorebookEntry:
    entry = mount.lorebook_entry
    return models.SessionLorebookEntry(
        id=int(entry.id),
        mount_id=int(mount.id),
        workspace_id=str(mount.workspace_id),
        story_id=int(mount.story_id),
        name=str(entry.name),
        content=str(entry.content or ""),
        description=str(entry.description or ""),
        tags=_parse_tags(entry.tags_json),
        enabled=bool(mount.enabled),
        sort_order=int(mount.sort_order),
    )


def _parse_tags(raw: str | None) -> tuple[str, ...]:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(item for item in data if isinstance(item, str))
