"""Services for lorebook reads and management."""

from __future__ import annotations

import json
import logging

from peewee import Database

from rpg_data import models
from rpg_data.repositories.lorebook_repo import LorebookEntryRepository
from rpg_data.repositories.records import (
    LorebookEntryRecord,
    SessionRecord,
    StoryLorebookEntryRecord,
    bind_database,
)
from rpg_data.repositories.story_lorebook_repo import StoryLorebookEntryRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository

__all__ = ["LorebookManagementService", "LorebookReadService"]

logger = logging.getLogger("rpg_data.lorebook")


class LorebookReadService:
    """Expose lorebook entries mounted to a session's story."""

    def __init__(self, database: Database) -> None:
        bind_database(database)

    def list_entries(
        self,
        session_id: str,
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

        result = [
            _to_session_lorebook_entry(row)
            for row in query.order_by(
                StoryLorebookEntryRecord.sort_order,
                StoryLorebookEntryRecord.id,
            )
        ]
        logger.debug(
            "listed lorebook entries session_id=%s workspace_id=%s story_id=%s count=%s names=%s",
            session_id,
            session.workspace_id,
            session.story_id,
            len(result),
            [entry.name for entry in result],
        )
        return result

    def list_enabled_entries(self, session_id: str) -> list[models.SessionLorebookEntry]:
        """Compatibility alias for mounted lorebook entries."""

        return self.list_entries(session_id)

    def get_entry(
        self,
        session_id: str,
        name: str,
    ) -> models.SessionLorebookEntry | None:
        """Return one mounted lorebook entry by name."""

        for entry in self.list_entries(session_id):
            if entry.name == name:
                logger.debug("loaded lorebook entry session_id=%s name=%s entry_id=%s", session_id, name, entry.id)
                return entry
        logger.debug("lorebook entry not found session_id=%s name=%s", session_id, name)
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


class LorebookManagementService:
    """Manage workspace lorebook entries and story mounts."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        self._workspaces = WorkspaceRepository(database)
        self._stories = StoryRepository(database)
        self._entries = LorebookEntryRepository(database)
        self._mounts = StoryLorebookEntryRepository(database)

    def list_entries(self, workspace_id: str) -> list[models.LorebookEntry] | None:
        if self._workspaces.get(workspace_id) is None:
            return None
        return self._entries.list(workspace_id)

    def create_entry(
        self,
        workspace_id: str,
        *,
        name: str,
        content: str = "",
        description: str = "",
        tags: list[str] | tuple[str, ...] = (),
        metadata: dict[str, object] | None = None,
    ) -> models.LorebookEntry | None:
        if self._workspaces.get(workspace_id) is None:
            return None
        entry = self._entries.create(
            workspace_id,
            name.strip(),
            content=content,
            description=description,
            tags_json=_dump_tags(tags),
            metadata_json=_dump_metadata(metadata),
        )
        logger.info("created lorebook entry workspace_id=%s entry_id=%s name=%s", workspace_id, entry.id, entry.name)
        return entry

    def update_entry(
        self,
        workspace_id: str,
        entry_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> models.LorebookEntry | None:
        entry = self._entries.get(entry_id)
        if entry is None or entry.workspace_id != workspace_id:
            return None
        updated = self._entries.update(
            entry_id,
            name=name.strip() if name is not None else None,
            content=content,
            description=description,
            tags_json=_dump_tags(tags) if tags is not None else None,
            metadata_json=_dump_metadata(metadata) if metadata is not None else None,
        )
        if updated is None:
            return None
        logger.info("updated lorebook entry workspace_id=%s entry_id=%s name=%s", workspace_id, entry_id, updated.name)
        return updated

    def delete_entry(
        self,
        workspace_id: str,
        entry_id: int,
    ) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None or entry.workspace_id != workspace_id:
            return False
        deleted = self._entries.delete(entry_id)
        logger.info(
            "deleted lorebook entry workspace_id=%s entry_id=%s deleted=%s",
            workspace_id,
            entry_id,
            deleted,
        )
        return deleted

    def list_story_entries(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryLorebookEntryDetail] | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        rows = (
            StoryLorebookEntryRecord
            .select(StoryLorebookEntryRecord, LorebookEntryRecord)
            .join(LorebookEntryRecord)
            .where(
                (StoryLorebookEntryRecord.workspace == workspace_id)
                & (StoryLorebookEntryRecord.story == story_id)
            )
            .order_by(StoryLorebookEntryRecord.sort_order, StoryLorebookEntryRecord.id)
        )
        return [_to_story_lorebook_entry_detail(row) for row in rows]

    def mount_entry(
        self,
        workspace_id: str,
        story_id: int,
        entry_id: int,
    ) -> models.StoryLorebookEntryDetail | None:
        if not self._story_belongs_to_workspace(workspace_id, story_id):
            return None
        entry = self._entries.get(entry_id)
        if entry is None or entry.workspace_id != workspace_id:
            return None
        with self._database.atomic():
            mount = self._mounts.mount(workspace_id, story_id, entry_id)
        logger.info(
            "mounted lorebook entry workspace_id=%s story_id=%s entry_id=%s mount_id=%s",
            workspace_id,
            story_id,
            entry_id,
            mount.id,
        )
        return _to_story_lorebook_entry_detail(_get_mount_record(mount.id))

    def unmount_entry(
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
            "unmounted lorebook entry workspace_id=%s story_id=%s mount_id=%s deleted=%s",
            workspace_id,
            story_id,
            mount_id,
            deleted,
        )
        return deleted

    def _story_belongs_to_workspace(self, workspace_id: str, story_id: int) -> bool:
        story = self._stories.get(story_id)
        return story is not None and story.workspace_id == workspace_id


def _to_story_lorebook_entry_detail(mount_row: StoryLorebookEntryRecord) -> models.StoryLorebookEntryDetail:
    entry = mount_row.lorebook_entry
    mount = models.StoryLorebookEntry(
        id=int(mount_row.id),
        workspace_id=str(mount_row.workspace_id),
        story_id=int(mount_row.story_id),
        lorebook_entry_id=int(mount_row.lorebook_entry_id),
        sort_order=int(mount_row.sort_order),
        metadata_json=str(mount_row.metadata_json or "{}"),
        version=int(mount_row.version),
        created_at=str(mount_row.created_at),
        updated_at=str(mount_row.updated_at),
    )
    return models.StoryLorebookEntryDetail(
        mount=mount,
        entry=models.LorebookEntry(
            id=int(entry.id),
            workspace_id=str(entry.workspace_id),
            name=str(entry.name),
            content=str(entry.content or ""),
            description=str(entry.description or ""),
            tags_json=str(entry.tags_json or "[]"),
            metadata_json=str(entry.metadata_json or "{}"),
            version=int(entry.version),
            created_at=str(entry.created_at),
            updated_at=str(entry.updated_at),
        ),
    )


def _get_mount_record(mount_id: int) -> StoryLorebookEntryRecord:
    row = (
        StoryLorebookEntryRecord
        .select(StoryLorebookEntryRecord, LorebookEntryRecord)
        .join(LorebookEntryRecord)
        .where(StoryLorebookEntryRecord.id == mount_id)
        .first()
    )
    if row is None:
        raise LookupError(f"Lorebook mount not found after create: {mount_id}")
    return row


def _dump_tags(tags: list[str] | tuple[str, ...]) -> str:
    cleaned = [str(tag).strip() for tag in tags if str(tag).strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def _dump_metadata(metadata: dict[str, object] | None) -> str:
    return json.dumps(metadata or {}, ensure_ascii=False)
