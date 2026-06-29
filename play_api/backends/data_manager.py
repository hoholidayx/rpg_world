"""Data manager backend provider for Play API."""

from __future__ import annotations

import json
from pathlib import Path

from rpg_data import models
from rpg_data.services import DataServiceGateway, get_data_service_gateway
from rpg_data.settings import get_database_path
from rpg_data.bootstrap import scan_orphan_runtime_data


class DataManagerBackend:
    """Read Play-facing metadata from the rpg_data database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._database_path = (
            Path(db_path).expanduser()
            if db_path is not None
            else get_database_path()
        )
        self._gateway: DataServiceGateway = get_data_service_gateway(self._database_path)
        self._gateway.initialize()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def close(self) -> None:
        self._gateway.close()

    async def list_workspaces(self) -> list[dict[str, object]]:
        return [_workspace_summary(workspace) for workspace in self._gateway.catalog.list_workspaces()]

    async def list_stories(self, workspace: str) -> list[dict[str, object]] | None:
        stories = self._gateway.catalog.list_stories(workspace)
        if stories is None:
            return None
        return [_story_summary(story) for story in stories]

    async def list_sessions(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        sessions = self._gateway.catalog.list_sessions(workspace, story_id)
        if sessions is None:
            return None
        return [_session_summary(session) for session in sessions]

    async def create_session(
        self,
        workspace: str,
        story_id: int,
        *,
        title: str = "",
        description: str = "",
    ) -> dict[str, object] | None:
        session = self._gateway.catalog.create_session(
            workspace,
            story_id,
            title=title,
            description=description,
        )
        if session is None:
            return None
        return _session_summary(session)

    async def get_session(
        self,
        session_id: str,
    ) -> dict[str, object] | None:
        session = self._gateway.catalog.get_session(session_id)
        if session is None:
            return None
        return _session_summary(session)

    async def scan_orphan_runtime(self) -> dict[str, list[dict[str, str]]]:
        return scan_orphan_runtime_data(self._gateway.database)

    async def list_lorebook_entries(self, workspace: str) -> list[dict[str, object]] | None:
        entries = self._gateway.lorebook_management.list_entries(workspace)
        if entries is None:
            return None
        return [_lorebook_entry_summary(entry) for entry in entries]

    async def create_lorebook_entry(
        self,
        workspace: str,
        *,
        name: str,
        content: str = "",
        description: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        entry = self._gateway.lorebook_management.create_entry(
            workspace,
            name=name,
            content=content,
            description=description,
            tags=tags or [],
            metadata=metadata,
        )
        if entry is None:
            return None
        return _lorebook_entry_summary(entry)

    async def get_lorebook_entry(
        self,
        workspace: str,
        entry_id: int,
    ) -> dict[str, object] | None:
        entries = self._gateway.lorebook_management.list_entries(workspace)
        if entries is None:
            return None
        for entry in entries:
            if int(entry.id) == int(entry_id):
                return _lorebook_entry_summary(entry)
        return None

    async def update_lorebook_entry(
        self,
        workspace: str,
        entry_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        entry = self._gateway.lorebook_management.update_entry(
            workspace,
            entry_id,
            name=name,
            content=content,
            description=description,
            tags=tags,
            metadata=metadata,
        )
        if entry is None:
            return None
        return _lorebook_entry_summary(entry)

    async def delete_lorebook_entry(
        self,
        workspace: str,
        entry_id: int,
    ) -> bool:
        return self._gateway.lorebook_management.delete_entry(workspace, entry_id)

    async def list_story_lorebook_entries(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        entries = self._gateway.lorebook_management.list_story_entries(workspace, story_id)
        if entries is None:
            return None
        return [_mounted_lorebook_entry_summary(entry) for entry in entries]

    async def mount_lorebook_entry(
        self,
        workspace: str,
        story_id: int,
        entry_id: int,
    ) -> dict[str, object] | None:
        entry = self._gateway.lorebook_management.mount_entry(workspace, story_id, entry_id)
        if entry is None:
            return None
        return _mounted_lorebook_entry_summary(entry)

    async def get_lorebook_mount(
        self,
        workspace: str,
        story_id: int,
        mount_id: int,
    ) -> dict[str, object] | None:
        entries = self._gateway.lorebook_management.list_story_entries(workspace, story_id)
        if entries is None:
            return None
        for entry in entries:
            if int(entry.mount.id) == int(mount_id):
                return _mounted_lorebook_entry_summary(entry)
        return None

    async def unmount_lorebook_entry(
        self,
        workspace: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None:
        return self._gateway.lorebook_management.unmount_entry(workspace, story_id, mount_id)


def _workspace_summary(workspace: models.Workspace) -> dict[str, object]:
    description = str(workspace.description or "")
    return {
        "id": str(workspace.id),
        "name": str(workspace.name),
        "description": description or None,
    }


def _story_summary(story: models.Story) -> dict[str, object]:
    return {
        "id": int(story.id),
        "workspace": str(story.workspace_id),
        "title": str(story.title),
        "summary": str(story.summary or "") or None,
        "description": str(story.description or "") or None,
        "created_at": str(story.created_at),
        "updated_at": str(story.updated_at),
    }


def _session_summary(session: models.Session) -> dict[str, object]:
    return {
        "id": str(session.id),
        "workspace": str(session.workspace_id),
        "story_id": int(session.story_id),
        "title": str(session.title or session.id),
        "description": str(session.description or "") or None,
        "created_at": str(session.created_at),
        "updated_at": str(session.updated_at),
    }


def _lorebook_entry_summary(entry: models.LorebookEntry) -> dict[str, object]:
    return {
        "id": int(entry.id),
        "workspace_id": str(entry.workspace_id),
        "name": str(entry.name),
        "content": str(entry.content or ""),
        "description": str(entry.description or ""),
        "tags": list(_parse_tags(entry.tags_json)),
        "metadata": _parse_metadata(entry.metadata_json),
        "version": int(entry.version),
        "created_at": str(entry.created_at),
        "updated_at": str(entry.updated_at),
    }


def _mounted_lorebook_entry_summary(detail: models.StoryLorebookEntryDetail) -> dict[str, object]:
    result = _lorebook_entry_summary(detail.entry)
    result.update(
        {
            "mount_id": int(detail.mount.id),
            "story_id": int(detail.mount.story_id),
        }
    )
    return result


def _parse_tags(raw: str | None) -> tuple[str, ...]:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(item for item in data if isinstance(item, str))


def _parse_metadata(raw: str | None) -> dict[str, object]:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
