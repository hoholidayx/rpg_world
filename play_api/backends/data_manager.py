"""Data manager backend provider for Play API."""

from __future__ import annotations

import json
from pathlib import Path

from rpg_data import models
from rpg_data.services import DataServiceGateway, get_data_service_gateway
from rpg_data.settings import get_database_path
from rpg_data.bootstrap import (
    delete_unindexed_runtime_item,
    delete_unindexed_runtime_items,
    scan_unindexed_runtime_data,
)


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

    async def create_story(
        self,
        workspace: str,
        *,
        title: str,
        summary: str = "",
        story_prompt: str = "",
        first_message: str = "",
    ) -> dict[str, object] | None:
        story = self._gateway.catalog.create_story(
            workspace,
            title=title,
            summary=summary,
            story_prompt=story_prompt,
            first_message=first_message,
        )
        if story is None:
            return None
        return _story_summary(story)

    async def update_story(
        self,
        workspace: str,
        story_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        story_prompt: str | None = None,
        first_message: str | None = None,
    ) -> dict[str, object] | None:
        story = self._gateway.catalog.update_story(
            workspace,
            story_id,
            title=title,
            summary=summary,
            story_prompt=story_prompt,
            first_message=first_message,
        )
        if story is None:
            return None
        return _story_summary(story)

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

    async def scan_unindexed_runtime(self, workspace: str) -> dict[str, list[dict[str, str]]] | None:
        return scan_unindexed_runtime_data(self._gateway.database, workspace)

    async def delete_unindexed_runtime_item(self, item: dict[str, str]) -> bool | None:
        return delete_unindexed_runtime_item(self._gateway.database, item)

    async def delete_unindexed_runtime_items(self, items: list[dict[str, str]]) -> bool | None:
        return delete_unindexed_runtime_items(self._gateway.database, items)

    async def list_characters(self, workspace: str) -> list[dict[str, object]] | None:
        characters = self._gateway.character_management.list_characters(workspace)
        if characters is None:
            return None
        return [
            _character_summary(
                character,
                self._gateway.character_management.list_details(workspace, int(character.id)) or [],
            )
            for character in characters
        ]

    async def create_character(
        self,
        workspace: str,
        *,
        name: str,
        personality: str = "",
        content: str = "",
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        character = self._gateway.character_management.create_character(
            workspace,
            name=name,
            personality=personality,
            content=content,
            metadata=metadata,
        )
        if character is None:
            return None
        return _character_summary(
            character,
            self._gateway.character_management.list_details(workspace, int(character.id)) or [],
        )

    async def get_character(
        self,
        workspace: str,
        character_id: int,
    ) -> dict[str, object] | None:
        characters = self._gateway.character_management.list_characters(workspace)
        if characters is None:
            return None
        for character in characters:
            if int(character.id) == int(character_id):
                return _character_summary(
                    character,
                    self._gateway.character_management.list_details(workspace, int(character.id)) or [],
                )
        return None

    async def update_character(
        self,
        workspace: str,
        character_id: int,
        *,
        name: str | None = None,
        personality: str | None = None,
        content: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        character = self._gateway.character_management.update_character(
            workspace,
            character_id,
            name=name,
            personality=personality,
            content=content,
            metadata=metadata,
        )
        if character is None:
            return None
        return _character_summary(
            character,
            self._gateway.character_management.list_details(workspace, int(character.id)) or [],
        )

    async def delete_character(
        self,
        workspace: str,
        character_id: int,
    ) -> bool:
        return self._gateway.character_management.delete_character(workspace, character_id)

    async def create_character_detail(
        self,
        workspace: str,
        character_id: int,
        *,
        name: str,
        content: str = "",
        tags: list[str] | None = None,
        sort_order: int = 0,
    ) -> dict[str, object] | None:
        detail = self._gateway.character_management.create_detail(
            workspace,
            character_id,
            name=name,
            content=content,
            tags=tags or [],
            sort_order=sort_order,
        )
        if detail is None:
            return None
        return _character_detail_summary(detail)

    async def update_character_detail(
        self,
        workspace: str,
        character_id: int,
        detail_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        sort_order: int | None = None,
    ) -> dict[str, object] | None:
        detail = self._gateway.character_management.update_detail(
            workspace,
            character_id,
            detail_id,
            name=name,
            content=content,
            tags=tags,
            sort_order=sort_order,
        )
        if detail is None:
            return None
        return _character_detail_summary(detail)

    async def delete_character_detail(
        self,
        workspace: str,
        character_id: int,
        detail_id: int,
    ) -> bool:
        return self._gateway.character_management.delete_detail(workspace, character_id, detail_id)

    async def list_story_characters(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        characters = self._gateway.character_management.list_story_characters(workspace, story_id)
        if characters is None:
            return None
        return [
            _mounted_character_summary(
                item,
                self._gateway.character_management.list_details(workspace, int(item.character.id)) or [],
            )
            for item in characters
        ]

    async def mount_character(
        self,
        workspace: str,
        story_id: int,
        character_id: int,
    ) -> dict[str, object] | None:
        character = self._gateway.character_management.mount_character(workspace, story_id, character_id)
        if character is None:
            return None
        return _mounted_character_summary(
            character,
            self._gateway.character_management.list_details(workspace, int(character.character.id)) or [],
        )

    async def unmount_character(
        self,
        workspace: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None:
        return self._gateway.character_management.unmount_character(workspace, story_id, mount_id)

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

    async def list_status_templates(
        self,
        workspace: str,
        status_kind: str | None = None,
    ) -> list[dict[str, object]] | None:
        if not _workspace_exists(self._gateway, workspace):
            return None
        return [
            _status_template_summary(template)
            for template in self._gateway.status.list_templates(workspace, status_kind=status_kind)
        ]

    async def create_status_template(
        self,
        workspace: str,
        *,
        name: str,
        status_kind: str,
        document: models.StatusTableDocument,
        description: str = "",
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        if not _workspace_exists(self._gateway, workspace):
            return None
        template = self._gateway.status.create_template(
            workspace,
            name,
            status_kind=status_kind,
            document=document,
            description=description,
            sort_order=sort_order,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        return _status_template_summary(template)

    async def update_status_template(
        self,
        workspace: str,
        template_id: int,
        *,
        name: str | None = None,
        status_kind: str | None = None,
        document: models.StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> dict[str, object] | None:
        template = self._gateway.status.get_template(template_id)
        if template is None or template.workspace_id != workspace:
            return None
        updated = self._gateway.status.update_template(
            template_id,
            name=name,
            status_kind=status_kind,
            document=document,
            description=description,
            sort_order=sort_order,
        )
        return _status_template_summary(updated)

    async def delete_status_template(self, workspace: str, template_id: int) -> bool | None:
        template = self._gateway.status.get_template(template_id)
        if template is None or template.workspace_id != workspace:
            return None
        self._gateway.status.delete_template(template_id)
        return True

    async def list_story_status_mounts(self, workspace: str, story_id: int) -> list[dict[str, object]] | None:
        stories = self._gateway.catalog.list_stories(workspace)
        if stories is None or not any(int(story.id) == int(story_id) for story in stories):
            return None
        return [
            _status_mount_summary(mount)
            for mount in self._gateway.status.list_story_mounts(workspace, story_id)
        ]

    async def mount_status_template(
        self,
        workspace: str,
        story_id: int,
        template_id: int,
        *,
        sort_order: int = 0,
    ) -> dict[str, object] | None:
        try:
            mount = self._gateway.status.mount_template(workspace, story_id, template_id, sort_order=sort_order)
        except FileNotFoundError:
            return None
        return _status_mount_summary(mount)

    async def unmount_status_template(self, workspace: str, story_id: int, mount_id: int) -> bool | None:
        mounts = self._gateway.status.list_story_mounts(workspace, story_id)
        if not any(int(mount.id) == int(mount_id) for mount in mounts):
            return None
        self._gateway.status.unmount_template(mount_id)
        return True

    async def list_session_status_tables(
        self,
        session_id: str,
        status_kind: str | None = None,
    ) -> list[dict[str, object]] | None:
        if self._gateway.catalog.get_session(session_id) is None:
            return None
        return [
            _session_status_table_summary(table)
            for table in self._gateway.status.list_tables(session_id, status_kind=status_kind)
        ]

    async def create_session_status_table(
        self,
        session_id: str,
        *,
        name: str,
        status_kind: str,
        document: models.StatusTableDocument,
        description: str = "",
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        if self._gateway.catalog.get_session(session_id) is None:
            return None
        table = self._gateway.status.create_table(
            session_id,
            name,
            status_kind=status_kind,
            document=document,
            description=description,
            sort_order=sort_order,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        return _session_status_table_summary(table)

    async def update_session_status_table(
        self,
        session_id: str,
        table_id: int,
        *,
        name: str | None = None,
        document: models.StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> dict[str, object] | None:
        try:
            table = self._gateway.status.get_table_by_id(table_id)
        except FileNotFoundError:
            return None
        if table.session_id != session_id:
            return None
        table = self._gateway.status.update_table(
            table_id,
            name=name,
            document=document,
            description=description,
            sort_order=sort_order,
        )
        return _session_status_table_summary(table)

    async def delete_session_status_table(self, session_id: str, table_id: int) -> bool | None:
        try:
            table = self._gateway.status.get_table_by_id(table_id)
        except FileNotFoundError:
            return None
        if table.session_id != session_id:
            return None
        self._gateway.status.delete_table(table_id)
        return True


def _workspace_summary(workspace: models.Workspace) -> dict[str, object]:
    description = str(workspace.description or "")
    return {
        "id": str(workspace.id),
        "name": str(workspace.name),
        "description": description or None,
    }


def _workspace_exists(gateway: DataServiceGateway, workspace: str) -> bool:
    return any(item.id == workspace for item in gateway.catalog.list_workspaces())


def _story_summary(story: models.Story) -> dict[str, object]:
    return {
        "id": int(story.id),
        "workspace": str(story.workspace_id),
        "title": str(story.title),
        "summary": str(story.summary or "") or None,
        "story_prompt": str(story.story_prompt or ""),
        "first_message": str(story.first_message or ""),
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


def _character_summary(
    character: models.Character,
    details: list[models.CharacterDetail],
) -> dict[str, object]:
    return {
        "id": int(character.id),
        "workspace_id": str(character.workspace_id),
        "name": str(character.name),
        "personality": str(character.personality or ""),
        "content": str(character.content or ""),
        "metadata": _parse_metadata(character.metadata_json),
        "details": [_character_detail_summary(detail) for detail in details],
        "version": int(character.version),
        "created_at": str(character.created_at),
        "updated_at": str(character.updated_at),
    }


def _character_detail_summary(detail: models.CharacterDetail) -> dict[str, object]:
    return {
        "id": int(detail.id),
        "character_id": int(detail.character_id),
        "name": str(detail.name),
        "content": str(detail.content or ""),
        "tags": list(_parse_tags(detail.tags_json)),
        "sort_order": int(detail.sort_order),
        "version": int(detail.version),
        "created_at": str(detail.created_at),
        "updated_at": str(detail.updated_at),
    }


def _mounted_character_summary(
    detail: models.StoryCharacterDetail,
    details: list[models.CharacterDetail],
) -> dict[str, object]:
    result = _character_summary(detail.character, details)
    result.update(
        {
            "mount_id": int(detail.mount.id),
            "story_id": int(detail.mount.story_id),
        }
    )
    return result


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


def _status_document_summary(document: models.StatusTableDocument) -> dict[str, object]:
    return {
        "key_column": document.key_column,
        "value_column": document.value_column,
        "rows": [
            {
                "key": row.key,
                "value": row.value,
                "runtime_key_locked": row.runtime_key_locked,
                "metadata": dict(row.metadata),
            }
            for row in document.rows
        ],
        "metadata": dict(document.metadata),
    }


def _status_template_summary(template: models.StatusTableTemplate) -> dict[str, object]:
    result = {
        "id": int(template.id),
        "workspace_id": str(template.workspace_id),
        "name": str(template.name),
        "status_kind": str(template.status_kind),
        "description": str(template.description or ""),
        "sort_order": int(template.sort_order),
        "metadata": _parse_metadata(template.metadata_json),
        "version": int(template.version),
        "created_at": str(template.created_at),
        "updated_at": str(template.updated_at),
    }
    result.update(_status_document_summary(template.document))
    return result


def _status_mount_summary(mount: models.StoryStatusTable) -> dict[str, object]:
    return {
        "id": int(mount.id),
        "workspace_id": str(mount.workspace_id),
        "story_id": int(mount.story_id),
        "status_table_id": int(mount.status_table_id),
        "table_name": str(mount.table_name),
        "status_kind": str(mount.status_kind),
        "description": str(mount.description or ""),
        "sort_order": int(mount.sort_order),
        "metadata": _parse_metadata(mount.metadata_json),
        "version": int(mount.version),
        "created_at": str(mount.created_at),
        "updated_at": str(mount.updated_at),
    }


def _session_status_table_summary(table: models.SessionStatusTable) -> dict[str, object]:
    result = {
        "id": int(table.id),
        "session_id": str(table.session_id),
        "workspace_id": str(table.workspace_id),
        "story_id": int(table.story_id),
        "source_table_id": table.source_table_id,
        "origin": str(table.origin),
        "name": str(table.name),
        "status_kind": str(table.status_kind),
        "description": str(table.description or ""),
        "sort_order": int(table.sort_order),
        "metadata": _parse_metadata(table.metadata_json),
        "version": int(table.version),
        "created_at": str(table.created_at),
        "updated_at": str(table.updated_at),
    }
    result.update(_status_document_summary(table.document))
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
