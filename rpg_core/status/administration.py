"""Application policy for Story and Session status-table administration."""

from __future__ import annotations

from typing import Protocol

from rpg_core.scene.status import SceneStatusService
from rpg_data.model.status import (
    STATUS_KIND_NORMAL,
    SessionStatusTable,
    StatusKind,
    StatusTableDocument,
    StoryStatusTable,
    validate_status_kind,
)


class StatusTableAdministrationDataPort(Protocol):
    def list_story_tables(
        self,
        workspace_id: str,
        story_id: int,
        *,
        status_kind: str | None = None,
    ) -> list[StoryStatusTable]: ...

    def get_story_table(
        self,
        story_status_table_id: int,
    ) -> StoryStatusTable | None: ...

    def create_story_table(
        self,
        workspace_id: str,
        story_id: int,
        name: str,
        *,
        status_kind: str = STATUS_KIND_NORMAL,
        story_character_id: int | None = None,
        document: StatusTableDocument | None = None,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> StoryStatusTable: ...

    def update_story_table(
        self,
        workspace_id: str,
        story_id: int,
        story_status_table_id: int,
        *,
        name: str | None = None,
        status_kind: str | None = None,
        story_character_id: int | None = None,
        update_story_character: bool = False,
        document: StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> StoryStatusTable: ...

    def delete_story_table(
        self,
        workspace_id: str,
        story_id: int,
        story_status_table_id: int,
    ) -> None: ...

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
    """Apply Scene/Status product rules around typed persistence primitives."""

    def __init__(self, data: StatusTableAdministrationDataPort) -> None:
        self._data = data

    def list_story_tables(
        self,
        workspace_id: str,
        story_id: int,
        *,
        status_kind: str | None = None,
    ) -> list[StoryStatusTable]:
        return self._data.list_story_tables(
            workspace_id,
            story_id,
            status_kind=status_kind,
        )

    def create_story_table(
        self,
        workspace_id: str,
        story_id: int,
        name: str,
        *,
        status_kind: str | StatusKind = STATUS_KIND_NORMAL,
        story_character_id: int | None = None,
        document: StatusTableDocument,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> StoryStatusTable:
        kind = validate_status_kind(status_kind)
        return self._data.create_story_table(
            workspace_id,
            story_id,
            name,
            status_kind=kind,
            story_character_id=story_character_id,
            document=SceneStatusService.prepare_document(kind, document),
            description=description,
            sort_order=sort_order,
            metadata_json=metadata_json,
        )

    def update_story_table(
        self,
        workspace_id: str,
        story_id: int,
        story_status_table_id: int,
        *,
        name: str | None = None,
        status_kind: str | StatusKind | None = None,
        story_character_id: int | None = None,
        update_story_character: bool = False,
        document: StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> StoryStatusTable:
        current = self._require_story_table(
            workspace_id,
            story_id,
            story_status_table_id,
        )
        kind = (
            current.status_kind
            if status_kind is None
            else validate_status_kind(status_kind)
        )
        if document is not None:
            prepared = SceneStatusService.prepare_document(kind, document)
        elif kind is not current.status_kind:
            prepared = SceneStatusService.prepare_document(kind, current.document)
        else:
            prepared = None
        return self._data.update_story_table(
            workspace_id,
            story_id,
            story_status_table_id,
            name=name,
            status_kind=kind,
            story_character_id=story_character_id,
            update_story_character=update_story_character,
            document=prepared,
            description=description,
            sort_order=sort_order,
        )

    def delete_story_table(
        self,
        workspace_id: str,
        story_id: int,
        story_status_table_id: int,
    ) -> None:
        self._require_story_table(workspace_id, story_id, story_status_table_id)
        self._data.delete_story_table(
            workspace_id,
            story_id,
            story_status_table_id,
        )

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

    def _require_story_table(
        self,
        workspace_id: str,
        story_id: int,
        story_status_table_id: int,
    ) -> StoryStatusTable:
        table = self._data.get_story_table(story_status_table_id)
        if (
            table is None
            or table.workspace_id != workspace_id
            or table.story_id != story_id
        ):
            raise FileNotFoundError(
                "Story status table not found: "
                f"{workspace_id}/{story_id}/{story_status_table_id}"
            )
        return table


__all__ = [
    "StatusTableAdministrationDataPort",
    "StatusTableAdministrationService",
]
