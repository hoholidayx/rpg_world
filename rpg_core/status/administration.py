"""Application service for Status-table administration policy."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from rpg_core.scene.status import SceneStatusService
from rpg_data.model.status import (
    STATUS_KIND_NORMAL,
    STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE,
    STORY_STATUS_MOUNT_ORIGIN_SYSTEM,
    SessionStatusTable,
    StatusKind,
    StatusTableDocument,
    StatusTableTemplate,
    StoryStatusTable,
    validate_status_kind,
)


class StatusTableAdministrationDataPort(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...

    def list_templates(
        self,
        workspace_id: str,
        *,
        status_kind: str | None = None,
    ) -> list[StatusTableTemplate]: ...

    def get_template(self, template_id: int) -> StatusTableTemplate | None: ...

    def create_template(
        self,
        workspace_id: str,
        name: str,
        *,
        status_kind: str = STATUS_KIND_NORMAL,
        document: StatusTableDocument | None = None,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> StatusTableTemplate: ...

    def update_template(
        self,
        template_id: int,
        *,
        name: str | None = None,
        status_kind: str | None = None,
        document: StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> StatusTableTemplate: ...

    def has_template_mounts(self, template_id: int) -> bool: ...

    def delete_template(self, template_id: int) -> None: ...

    def list_story_mounts(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryStatusTable]: ...

    def get_story_mount(self, mount_id: int) -> StoryStatusTable: ...

    def mount_template(
        self,
        workspace_id: str,
        story_id: int,
        template_id: int,
        *,
        character_mount_id: int | None = None,
        mount_origin: str = STORY_STATUS_MOUNT_ORIGIN_SYSTEM,
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> StoryStatusTable: ...

    def update_story_mount_character(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
        *,
        character_mount_id: int | None,
    ) -> StoryStatusTable: ...

    def unmount_template(self, mount_id: int) -> None: ...

    def list_tables(
        self,
        session_id: str,
        status_kind: str | None = None,
    ) -> list[SessionStatusTable]: ...

    def get_table_for_session(
        self,
        session_id: str,
        table_id: int,
    ) -> SessionStatusTable: ...

    def create_table(
        self,
        session_id: str,
        table_name: str,
        *,
        status_kind: str = STATUS_KIND_NORMAL,
        document: StatusTableDocument | None = None,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> SessionStatusTable: ...

    def update_table(
        self,
        table_id: int,
        *,
        name: str | None = None,
        document: StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> SessionStatusTable: ...

    def delete_table(self, table_id: int) -> None: ...


class StatusTableAdministrationService:
    """Apply Status/Scene product rules around persistence primitives."""

    def __init__(self, data: StatusTableAdministrationDataPort) -> None:
        self._data = data

    def list_templates(
        self,
        workspace_id: str,
        *,
        status_kind: str | None = None,
    ) -> list[StatusTableTemplate]:
        return self._data.list_templates(workspace_id, status_kind=status_kind)

    def create_template(
        self,
        workspace_id: str,
        name: str,
        *,
        status_kind: str | StatusKind = STATUS_KIND_NORMAL,
        document: StatusTableDocument,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> StatusTableTemplate:
        kind = validate_status_kind(status_kind)
        return self._data.create_template(
            workspace_id,
            name,
            status_kind=kind,
            document=SceneStatusService.prepare_document(kind, document),
            description=description,
            sort_order=sort_order,
            metadata_json=metadata_json,
        )

    def update_template(
        self,
        workspace_id: str,
        template_id: int,
        *,
        name: str | None = None,
        status_kind: str | StatusKind | None = None,
        document: StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> StatusTableTemplate:
        current = self._require_template(workspace_id, template_id)
        kind = (
            current.status_kind
            if status_kind is None
            else validate_status_kind(status_kind)
        )
        if document is not None:
            prepared = SceneStatusService.prepare_document(kind, document)
        elif kind is not current.status_kind:
            prepared = SceneStatusService.prepare_document(
                kind,
                current.document,
            )
        else:
            prepared = None
        return self._data.update_template(
            template_id,
            name=name,
            status_kind=kind,
            document=prepared,
            description=description,
            sort_order=sort_order,
        )

    def delete_template(self, workspace_id: str, template_id: int) -> None:
        with self._data.transaction():
            self._require_template(workspace_id, template_id)
            if self._data.has_template_mounts(template_id):
                raise ValueError(f"Status template is mounted: {template_id}")
            self._data.delete_template(template_id)

    def list_story_mounts(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryStatusTable]:
        return self._data.list_story_mounts(workspace_id, story_id)

    def mount_template(
        self,
        workspace_id: str,
        story_id: int,
        template_id: int,
        *,
        character_mount_id: int | None = None,
        sort_order: int = 0,
    ) -> StoryStatusTable:
        return self._data.mount_template(
            workspace_id,
            story_id,
            template_id,
            character_mount_id=character_mount_id,
            mount_origin=STORY_STATUS_MOUNT_ORIGIN_SYSTEM,
            sort_order=sort_order,
        )

    def create_story_template(
        self,
        workspace_id: str,
        story_id: int,
        name: str,
        *,
        status_kind: str | StatusKind = STATUS_KIND_NORMAL,
        character_mount_id: int | None = None,
        document: StatusTableDocument,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> StoryStatusTable:
        with self._data.transaction():
            template = self.create_template(
                workspace_id,
                name,
                status_kind=status_kind,
                document=document,
                description=description,
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
            return self._data.mount_template(
                workspace_id,
                story_id,
                template.id,
                character_mount_id=character_mount_id,
                mount_origin=STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE,
                sort_order=sort_order,
                metadata_json=metadata_json,
            )

    def update_story_mount_character(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
        *,
        character_mount_id: int | None,
    ) -> StoryStatusTable:
        self._require_mount(workspace_id, story_id, mount_id)
        return self._data.update_story_mount_character(
            workspace_id,
            story_id,
            mount_id,
            character_mount_id=character_mount_id,
        )

    def unmount_template(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
    ) -> None:
        mount = self._require_mount(workspace_id, story_id, mount_id)
        if mount.mount_origin is STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE:
            raise ValueError(
                "Story-owned status template must be deleted through story "
                f"template endpoint: {mount_id}"
            )
        self._data.unmount_template(mount_id)

    def delete_story_template(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
    ) -> None:
        with self._data.transaction():
            mount = self._require_mount(workspace_id, story_id, mount_id)
            if mount.mount_origin is not STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE:
                raise ValueError(f"Story status mount is not story-owned: {mount_id}")
            self._data.unmount_template(mount_id)
            if self._data.has_template_mounts(mount.status_table_id):
                raise ValueError(
                    f"Story-owned status template remains mounted: {mount_id}"
                )
            self._data.delete_template(mount.status_table_id)

    def list_session_tables(
        self,
        session_id: str,
        *,
        status_kind: str | None = None,
    ) -> list[SessionStatusTable]:
        return self._data.list_tables(session_id, status_kind=status_kind)

    def create_session_table(
        self,
        session_id: str,
        name: str,
        *,
        status_kind: str | StatusKind = STATUS_KIND_NORMAL,
        document: StatusTableDocument,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> SessionStatusTable:
        kind = validate_status_kind(status_kind)
        return self._data.create_table(
            session_id,
            name,
            status_kind=kind,
            document=SceneStatusService.prepare_document(kind, document),
            description=description,
            sort_order=sort_order,
            metadata_json=metadata_json,
        )

    def update_session_table(
        self,
        session_id: str,
        table_id: int,
        *,
        name: str | None = None,
        document: StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> SessionStatusTable:
        current = self._data.get_table_for_session(session_id, table_id)
        prepared = (
            None
            if document is None
            else SceneStatusService.prepare_document(current.status_kind, document)
        )
        return self._data.update_table(
            table_id,
            name=name,
            document=prepared,
            description=description,
            sort_order=sort_order,
        )

    def delete_session_table(self, session_id: str, table_id: int) -> None:
        self._data.get_table_for_session(session_id, table_id)
        self._data.delete_table(table_id)

    def _require_template(
        self,
        workspace_id: str,
        template_id: int,
    ) -> StatusTableTemplate:
        template = self._data.get_template(template_id)
        if template is None or template.workspace_id != workspace_id:
            raise FileNotFoundError(
                f"Status template not found: {workspace_id}/{template_id}"
            )
        return template

    def _require_mount(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
    ) -> StoryStatusTable:
        mount = self._data.get_story_mount(mount_id)
        if mount.workspace_id != workspace_id or mount.story_id != story_id:
            raise FileNotFoundError(
                "Story status table mount not found: "
                f"{workspace_id}/{story_id}/{mount_id}"
            )
        return mount


__all__ = [
    "StatusTableAdministrationDataPort",
    "StatusTableAdministrationService",
]
