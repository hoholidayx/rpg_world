"""Status table service backed by SQLite document records."""

from __future__ import annotations

import json
import logging
from typing import Callable, Iterable, Mapping

from peewee import Database, DoesNotExist, IntegrityError, SQL

from rpg_data import models
from rpg_data.repositories.records import (
    SessionRecord,
    SessionStatusTableRecord,
    StatusTableTemplateRecord,
    StoryCharacterRecord,
    StoryRecord,
    StoryStatusTableRecord,
    WorkspaceRecord,
    bind_database,
)
from rpg_data.settings import resolve_workspace_root

__all__ = ["StatusTableService"]

logger = logging.getLogger("rpg_data.status")

SCENE_DEFAULT_LOCKED_KEYS = {"时间", "位置", "在场人物"}


class StatusTableService:
    """Manage status tables with SQL relations and JSON document columns."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        logger.debug("status table service initialized database=%s", database)

    # ------------------------------------------------------------------
    # Template table CRUD
    # ------------------------------------------------------------------

    def list_templates(
        self,
        workspace_id: str,
        *,
        status_kind: str | None = None,
    ) -> list[models.StatusTableTemplate]:
        query = StatusTableTemplateRecord.select().where(
            StatusTableTemplateRecord.workspace == workspace_id
        )
        if status_kind is not None:
            query = query.where(StatusTableTemplateRecord.status_kind == models.validate_status_kind(status_kind))
        query = query.order_by(
            StatusTableTemplateRecord.status_kind,
            StatusTableTemplateRecord.sort_order,
            StatusTableTemplateRecord.id,
        )
        result = [_to_template(row) for row in query]
        logger.debug(
            "listed status templates workspace_id=%s status_kind=%s count=%s",
            workspace_id,
            status_kind,
            len(result),
        )
        return result

    def get_template(self, template_id: int) -> models.StatusTableTemplate | None:
        row = StatusTableTemplateRecord.get_or_none(StatusTableTemplateRecord.id == template_id)
        if row is None:
            logger.debug("status template not found template_id=%s", template_id)
            return None
        return _to_template(row)

    def create_template(
        self,
        workspace_id: str,
        name: str,
        *,
        status_kind: str = models.STATUS_KIND_NORMAL,
        document: models.StatusTableDocument | None = None,
        headers: Iterable[str] = (),
        rows: Iterable[Iterable[str]] = (),
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StatusTableTemplate:
        _validate_name(name, "status table")
        self._workspace_root(workspace_id)
        kind = models.validate_status_kind(status_kind)
        output_document = _document_from_inputs(
            kind,
            document=document,
            headers=headers,
            rows=rows,
        )
        try:
            row = StatusTableTemplateRecord.create(
                workspace=workspace_id,
                name=name,
                status_kind=kind,
                description=description,
                document_json=models.serialize_status_document(output_document),
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
        except IntegrityError as exc:
            logger.warning("status template create conflict workspace_id=%s name=%s", workspace_id, name)
            raise ValueError(f"Status template already exists: {workspace_id}/{name}") from exc
        logger.info(
            "created status template template_id=%s workspace_id=%s status_kind=%s name=%s",
            row.id,
            workspace_id,
            kind,
            name,
        )
        return _to_template(row)

    def update_template(
        self,
        template_id: int,
        *,
        name: str | None = None,
        status_kind: str | None = None,
        document: models.StatusTableDocument | None = None,
        headers: Iterable[str] | None = None,
        rows: Iterable[Iterable[str]] | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> models.StatusTableTemplate:
        row = self._get_template_row(template_id)
        target_name = str(row.name) if name is None else name
        _validate_name(target_name, "status table")
        target_kind = str(row.status_kind) if status_kind is None else models.validate_status_kind(status_kind)
        output_document = _updated_document(
            _parse_row_document(row),
            target_kind,
            document=document,
            headers=headers,
            rows=rows,
        )
        row.name = target_name
        row.status_kind = target_kind
        row.document_json = models.serialize_status_document(output_document)
        if description is not None:
            row.description = description
        if sort_order is not None:
            row.sort_order = sort_order
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        try:
            row.save()
        except IntegrityError as exc:
            raise ValueError(f"Status template already exists: {row.workspace_id}/{target_name}") from exc
        logger.info("updated status template template_id=%s name=%s status_kind=%s", template_id, target_name, target_kind)
        return _to_template(self._get_template_row(template_id))

    def delete_template(self, template_id: int) -> None:
        row = self._get_template_row(template_id)
        if StoryStatusTableRecord.select().where(StoryStatusTableRecord.status_table == template_id).exists():
            raise ValueError(f"Status template is mounted: {template_id}")
        row.delete_instance()
        logger.info("deleted status template template_id=%s", template_id)

    # ------------------------------------------------------------------
    # Story mounts
    # ------------------------------------------------------------------

    def list_story_mounts(self, workspace_id: str, story_id: int) -> list[models.StoryStatusTable]:
        query = (
            StoryStatusTableRecord
            .select(StoryStatusTableRecord, StatusTableTemplateRecord)
            .join(StatusTableTemplateRecord)
            .where(
                (StoryStatusTableRecord.workspace == workspace_id)
                & (StoryStatusTableRecord.story == story_id)
            )
            .order_by(StoryStatusTableRecord.sort_order, StoryStatusTableRecord.id)
        )
        result = [_to_story_mount(row) for row in query]
        logger.debug("listed story status mounts workspace_id=%s story_id=%s count=%s", workspace_id, story_id, len(result))
        return result

    def mount_template(
        self,
        workspace_id: str,
        story_id: int,
        template_id: int,
        *,
        character_mount_id: int | None = None,
        mount_origin: str = models.STORY_STATUS_MOUNT_ORIGIN_SYSTEM,
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StoryStatusTable:
        story = self._get_story_row(story_id)
        if str(story.workspace_id) != workspace_id:
            raise FileNotFoundError(f"Story not found in workspace: {workspace_id}/{story_id}")
        template = self._get_template_row(template_id)
        if str(template.workspace_id) != workspace_id:
            raise FileNotFoundError(f"Status template not found in workspace: {workspace_id}/{template_id}")
        origin = models.validate_story_status_mount_origin(mount_origin)
        character_mount = self._get_story_character_mount(workspace_id, story_id, character_mount_id)
        try:
            row = StoryStatusTableRecord.create(
                workspace=workspace_id,
                story=story_id,
                status_table=template_id,
                story_character=None if character_mount is None else int(character_mount.id),
                mount_origin=origin,
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
        except IntegrityError as exc:
            raise ValueError(f"Status table already mounted to story: {story_id}/{template_id}") from exc
        logger.info("mounted status template mount_id=%s workspace_id=%s story_id=%s template_id=%s", row.id, workspace_id, story_id, template_id)
        return _to_story_mount(self._get_story_mount_row(int(row.id)))

    def create_story_template(
        self,
        workspace_id: str,
        story_id: int,
        name: str,
        *,
        status_kind: str = models.STATUS_KIND_NORMAL,
        character_mount_id: int | None = None,
        document: models.StatusTableDocument | None = None,
        headers: Iterable[str] = (),
        rows: Iterable[Iterable[str]] = (),
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StoryStatusTable:
        with self._database.atomic():
            template = self.create_template(
                workspace_id,
                name,
                status_kind=status_kind,
                document=document,
                headers=headers,
                rows=rows,
                description=description,
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
            return self.mount_template(
                workspace_id,
                story_id,
                template.id,
                character_mount_id=character_mount_id,
                mount_origin=models.STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE,
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
    ) -> models.StoryStatusTable:
        row = self._get_story_mount_row(mount_id)
        if str(row.workspace_id) != workspace_id or int(row.story_id) != int(story_id):
            raise FileNotFoundError(f"Story status table mount not found: {workspace_id}/{story_id}/{mount_id}")
        character_mount = self._get_story_character_mount(workspace_id, story_id, character_mount_id)
        row.story_character = None if character_mount is None else int(character_mount.id)
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        row.save()
        logger.info(
            "updated story status mount character mount_id=%s character_mount_id=%s",
            mount_id,
            character_mount_id,
        )
        return _to_story_mount(self._get_story_mount_row(mount_id))

    def unmount_template(self, mount_id: int) -> None:
        row = self._get_story_mount_row(mount_id)
        row.delete_instance()
        logger.info("unmounted status template mount_id=%s", mount_id)

    def delete_story_template_mount(self, workspace_id: str, story_id: int, mount_id: int) -> None:
        row = self._get_story_mount_row(mount_id)
        if str(row.workspace_id) != workspace_id or int(row.story_id) != int(story_id):
            raise FileNotFoundError(f"Story status table mount not found: {workspace_id}/{story_id}/{mount_id}")
        if str(row.mount_origin) != models.STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE:
            raise ValueError(f"Story status mount is not story-owned: {mount_id}")
        template_id = int(row.status_table_id)
        with self._database.atomic():
            row.delete_instance()
            self.delete_template(template_id)
        logger.info("deleted story status template mount_id=%s template_id=%s", mount_id, template_id)

    # ------------------------------------------------------------------
    # Session tables
    # ------------------------------------------------------------------

    def initialize_session_tables(self, session_id: str) -> list[models.SessionStatusTable]:
        session = self._get_session_row(session_id)
        if SessionStatusTableRecord.select().where(SessionStatusTableRecord.session == session_id).exists():
            return self.list_tables(session_id)
        workspace_id = str(session.workspace_id)
        story_id = int(session.story_id)
        mounts = list(
            StoryStatusTableRecord
            .select(StoryStatusTableRecord, StatusTableTemplateRecord)
            .join(StatusTableTemplateRecord)
            .where(
                (StoryStatusTableRecord.workspace == workspace_id)
                & (StoryStatusTableRecord.story == story_id)
            )
            .order_by(StoryStatusTableRecord.sort_order, StoryStatusTableRecord.id)
        )
        with self._database.atomic():
            for mount in mounts:
                template = mount.status_table
                SessionStatusTableRecord.create(
                    session=session_id,
                    workspace=workspace_id,
                    story=story_id,
                    source_table_id=int(template.id),
                    origin=models.STATUS_ORIGIN_TEMPLATE_COPY,
                    name=str(template.name),
                    status_kind=str(template.status_kind),
                    description=str(template.description or ""),
                    document_json=str(template.document_json),
                    sort_order=int(mount.sort_order),
                    metadata_json=_session_metadata_for_mount(str(template.metadata_json or "{}"), mount),
                )
        tables = self.list_tables(session_id)
        logger.info("initialized session status tables session_id=%s table_count=%s", session_id, len(tables))
        return tables

    def list_tables(
        self,
        session_id: str,
        status_kind: str | None = None,
        *,
        include_scene: bool = True,
    ) -> list[models.SessionStatusTable]:
        query = SessionStatusTableRecord.select().where(SessionStatusTableRecord.session == session_id)
        if status_kind is not None:
            query = query.where(SessionStatusTableRecord.status_kind == models.validate_status_kind(status_kind))
        if not include_scene:
            query = query.where(SessionStatusTableRecord.status_kind != models.STATUS_KIND_SCENE)
        query = query.order_by(
            SessionStatusTableRecord.status_kind,
            SessionStatusTableRecord.sort_order,
            SessionStatusTableRecord.id,
        )
        result = [_to_session_table(row) for row in query]
        logger.debug("listed session status tables session_id=%s status_kind=%s count=%s", session_id, status_kind, len(result))
        return result

    def list_context_tables(self, session_id: str) -> list[models.SessionStatusTable]:
        return self.list_tables(session_id, include_scene=False)

    def get_table(
        self,
        session_id: str,
        table_name: str,
        status_kind: str | None = None,
    ) -> models.SessionStatusTable:
        row = self._find_session_table(session_id, table_name, status_kind=status_kind)
        if row is None:
            raise FileNotFoundError(f"Status table not found: {session_id}/{table_name}")
        return _to_session_table(row)

    def get_table_by_id(self, table_id: int) -> models.SessionStatusTable:
        return _to_session_table(self._get_session_table_row(table_id))

    def create_table(
        self,
        session_id: str,
        table_name: str,
        *,
        status_kind: str = models.STATUS_KIND_NORMAL,
        document: models.StatusTableDocument | None = None,
        headers: Iterable[str] = (),
        rows: Iterable[Iterable[str]] = (),
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.SessionStatusTable:
        _validate_name(table_name, "session status table")
        session = self._get_session_row(session_id)
        kind = models.validate_status_kind(status_kind)
        output_document = _document_from_inputs(kind, document=document, headers=headers, rows=rows)
        try:
            row = SessionStatusTableRecord.create(
                session=session_id,
                workspace=str(session.workspace_id),
                story=int(session.story_id),
                source_table_id=None,
                origin=models.STATUS_ORIGIN_SESSION_NATIVE,
                name=table_name,
                status_kind=kind,
                description=description,
                document_json=models.serialize_status_document(output_document),
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
        except IntegrityError as exc:
            raise ValueError(f"Session status table already exists: {session_id}/{table_name}") from exc
        logger.info("created session status table table_id=%s session_id=%s name=%s", row.id, session_id, table_name)
        return _to_session_table(row)

    def save_table(
        self,
        table_id: int,
        document: models.StatusTableDocument,
    ) -> models.SessionStatusTable:
        row = self._get_session_table_row(table_id)
        row.document_json = models.serialize_status_document(_document_for_kind(str(row.status_kind), document))
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        row.save()
        return _to_session_table(row)

    def update_table(
        self,
        table_id: int,
        *,
        name: str | None = None,
        document: models.StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> models.SessionStatusTable:
        row = self._get_session_table_row(table_id)
        target_name = str(row.name) if name is None else name
        _validate_name(target_name, "session status table")
        row.name = target_name
        if document is not None:
            row.document_json = models.serialize_status_document(_document_for_kind(str(row.status_kind), document))
        if description is not None:
            row.description = description
        if sort_order is not None:
            row.sort_order = sort_order
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        try:
            row.save()
        except IntegrityError as exc:
            raise ValueError(f"Session status table already exists: {row.session_id}/{target_name}") from exc
        logger.info("updated session status table table_id=%s name=%s", table_id, target_name)
        return _to_session_table(self._get_session_table_row(table_id))

    def rename_table(self, table_id: int, new_name: str) -> models.SessionStatusTable:
        _validate_name(new_name, "session status table")
        row = self._get_session_table_row(table_id)
        row.name = new_name
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        try:
            row.save()
        except IntegrityError as exc:
            raise ValueError(f"Session status table already exists: {row.session_id}/{new_name}") from exc
        logger.info("renamed session status table table_id=%s new_name=%s", table_id, new_name)
        return _to_session_table(row)

    def delete_table(self, table_id: int) -> None:
        row = self._get_session_table_row(table_id)
        row.delete_instance()
        logger.info("deleted session status table table_id=%s", table_id)

    # ------------------------------------------------------------------
    # Key-value writes
    # ------------------------------------------------------------------

    def set_cell(
        self,
        table_id: int,
        row: int | models.StatusRowRef,
        column: int | str,
        value: str,
    ) -> models.SessionStatusTable:
        return self._update_table_data(table_id, lambda data: data.with_cell(row, column, value))

    def append_row(self, table_id: int, values: Iterable[str]) -> models.SessionStatusTable:
        row_values = _materialize_row_values(values)
        return self._update_table_data(table_id, lambda data: data.with_appended_row(row_values))

    def replace_row(
        self,
        table_id: int,
        row: int | models.StatusRowRef,
        values: Iterable[str],
    ) -> models.SessionStatusTable:
        row_values = _materialize_row_values(values)
        return self._update_table_data(table_id, lambda data: data.with_replaced_row(row, row_values))

    def delete_row(self, table_id: int, row: int | models.StatusRowRef) -> models.SessionStatusTable:
        return self._update_table_data(table_id, lambda data: data.with_deleted_row(row))

    def set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = models.STATUS_KEY_COLUMN,
        value_column: int | str = models.STATUS_VALUE_COLUMN,
    ) -> models.SessionStatusTable:
        if key_column == models.STATUS_KEY_COLUMN and value_column == models.STATUS_VALUE_COLUMN:
            current = self.get_table_by_id(table_id)
            return self.save_table(table_id, current.document.with_key_value(key, value))
        return self._update_table_data(
            table_id,
            lambda data: data.with_key_value(key, value, key_column=key_column, value_column=value_column),
        )

    def delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = models.STATUS_KEY_COLUMN,
    ) -> models.SessionStatusTable:
        if key_column == models.STATUS_KEY_COLUMN:
            current = self.get_table_by_id(table_id)
            return self.save_table(table_id, current.document.without_key(key))
        return self._update_table_data(table_id, lambda data: data.without_key(key, key_column=key_column))

    def runtime_set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = models.STATUS_KEY_COLUMN,
        value_column: int | str = models.STATUS_VALUE_COLUMN,
    ) -> models.SessionStatusTable:
        return self.set_key_value(table_id, key, value, key_column=key_column, value_column=value_column)

    def runtime_delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = models.STATUS_KEY_COLUMN,
    ) -> models.SessionStatusTable:
        current = self.get_table_by_id(table_id)
        document_row = current.document.row_for_key(key)
        if document_row is None:
            raise FileNotFoundError(f"Status table key not found: {key}")
        if document_row.runtime_key_locked:
            raise PermissionError(f"Status key is runtime locked: {key}")
        return self.delete_key_value(table_id, key, key_column=key_column)

    # ------------------------------------------------------------------
    # Scene helpers
    # ------------------------------------------------------------------

    def get_active_scene_table(self, session_id: str) -> models.SessionStatusTable | None:
        row = (
            SessionStatusTableRecord
            .select()
            .where(
                (SessionStatusTableRecord.session == session_id)
                & (SessionStatusTableRecord.status_kind == models.STATUS_KIND_SCENE)
            )
            .order_by(SessionStatusTableRecord.sort_order, SessionStatusTableRecord.id)
            .first()
        )
        return None if row is None else _to_session_table(row)

    def get_scene_attrs(self, session_id: str) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            return None
        return _rows_to_attrs(table.rows)

    def replace_scene_attrs(self, session_id: str, attrs: Mapping[str, str]) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            return None
        data = models.StatusTableData(
            headers=(models.STATUS_KEY_COLUMN, models.STATUS_VALUE_COLUMN),
            rows=tuple((str(key), str(value)) for key, value in attrs.items()),
        )
        updated = self._replace_table_data(table.id, data)
        return _rows_to_attrs(updated.rows)

    def set_scene_attr(self, session_id: str, key: str, value: str) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            return None
        updated = self.runtime_set_key_value(table.id, str(key), str(value))
        return _rows_to_attrs(updated.rows)

    def delete_scene_attr(self, session_id: str, key: str) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            return None
        try:
            table = self.runtime_delete_key_value(table.id, str(key))
        except (FileNotFoundError, PermissionError):
            pass
        return _rows_to_attrs(table.rows)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_table_data(
        self,
        table_id: int,
        transform: Callable[[models.StatusTableData], models.StatusTableData],
    ) -> models.SessionStatusTable:
        current = self.get_table_by_id(table_id)
        updated = transform(current.data)
        return self._replace_table_data(table_id, updated)

    def _replace_table_data(
        self,
        table_id: int,
        data: models.StatusTableData,
    ) -> models.SessionStatusTable:
        row = self._get_session_table_row(table_id)
        current = _parse_row_document(row)
        row.document_json = models.serialize_status_document(
            _document_for_kind(str(row.status_kind), current.with_data(data))
        )
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        row.save()
        return _to_session_table(row)

    def _workspace_root(self, workspace_id: str):
        try:
            row = WorkspaceRecord.get_by_id(workspace_id)
        except DoesNotExist as exc:
            raise FileNotFoundError(f"Workspace not found: {workspace_id}") from exc
        return resolve_workspace_root(str(row.root_path))

    def _get_template_row(self, template_id: int) -> StatusTableTemplateRecord:
        row = StatusTableTemplateRecord.get_or_none(StatusTableTemplateRecord.id == template_id)
        if row is None:
            raise FileNotFoundError(f"Status template not found: {template_id}")
        return row

    def _get_story_row(self, story_id: int) -> StoryRecord:
        try:
            return StoryRecord.get_by_id(story_id)
        except DoesNotExist as exc:
            raise FileNotFoundError(f"Story not found: {story_id}") from exc

    def _get_story_mount_row(self, mount_id: int) -> StoryStatusTableRecord:
        row = (
            StoryStatusTableRecord
            .select(StoryStatusTableRecord, StatusTableTemplateRecord)
            .join(StatusTableTemplateRecord)
            .where(StoryStatusTableRecord.id == mount_id)
            .first()
        )
        if row is None:
            raise FileNotFoundError(f"Story status table mount not found: {mount_id}")
        return row

    def _get_story_character_mount(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int | None,
    ) -> StoryCharacterRecord | None:
        if mount_id is None:
            return None
        row = StoryCharacterRecord.get_or_none(StoryCharacterRecord.id == mount_id)
        if row is None or str(row.workspace_id) != workspace_id or int(row.story_id) != int(story_id):
            raise FileNotFoundError(f"Story character mount not found: {workspace_id}/{story_id}/{mount_id}")
        return row

    def _get_session_row(self, session_id: str) -> SessionRecord:
        try:
            return SessionRecord.get_by_id(session_id)
        except DoesNotExist as exc:
            raise FileNotFoundError(f"Session not found: {session_id}") from exc

    def _get_session_table_row(self, table_id: int) -> SessionStatusTableRecord:
        row = SessionStatusTableRecord.get_or_none(SessionStatusTableRecord.id == table_id)
        if row is None:
            raise FileNotFoundError(f"Session status table not found: {table_id}")
        return row

    def _find_session_table(
        self,
        session_id: str,
        table_name: str,
        *,
        status_kind: str | None = None,
    ) -> SessionStatusTableRecord | None:
        query = SessionStatusTableRecord.select().where(
            (SessionStatusTableRecord.session == session_id)
            & (SessionStatusTableRecord.name == table_name)
        )
        if status_kind is not None:
            query = query.where(SessionStatusTableRecord.status_kind == models.validate_status_kind(status_kind))
        return query.first()


def _to_template(row: StatusTableTemplateRecord) -> models.StatusTableTemplate:
    return models.StatusTableTemplate(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        name=str(row.name),
        status_kind=str(row.status_kind),
        description=str(row.description or ""),
        document=_parse_row_document(row),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_story_mount(row: StoryStatusTableRecord) -> models.StoryStatusTable:
    template = row.status_table
    return models.StoryStatusTable(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        status_table_id=int(row.status_table_id),
        story_character_mount_id=_story_character_mount_id(row),
        table_name=str(template.name),
        mount_origin=models.validate_story_status_mount_origin(str(row.mount_origin)),
        status_kind=str(template.status_kind),
        description=str(template.description or ""),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_session_table(row: SessionStatusTableRecord) -> models.SessionStatusTable:
    source_table_id = None if row.source_table_id is None else int(row.source_table_id)
    return models.SessionStatusTable(
        id=int(row.id),
        session_id=str(row.session_id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        source_table_id=source_table_id,
        origin=str(row.origin),
        name=str(row.name),
        status_kind=str(row.status_kind),
        description=str(row.description or ""),
        document=_parse_row_document(row),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _parse_row_document(row: object) -> models.StatusTableDocument:
    return models.parse_status_document(str(getattr(row, "document_json", "")))


def _session_metadata_for_mount(template_metadata_json: str, mount: StoryStatusTableRecord) -> str:
    metadata = _parse_metadata_json(template_metadata_json)
    character_mount_id = _story_character_mount_id(mount)
    character_id = None
    if character_mount_id is not None:
        try:
            character_id = int(mount.story_character.character_id)
        except DoesNotExist:
            character_id = None
    metadata["storyStatusMount"] = {
        "mountId": int(mount.id),
        "mountOrigin": models.validate_story_status_mount_origin(str(mount.mount_origin)),
        "characterMountId": character_mount_id,
        "characterId": character_id,
    }
    return json.dumps(metadata, ensure_ascii=False)


def _story_character_mount_id(row: StoryStatusTableRecord) -> int | None:
    raw_value = row.__data__.get("story_character")
    return None if raw_value is None else int(raw_value)


def _parse_metadata_json(raw: str) -> dict[str, object]:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _document_from_inputs(
    status_kind: str,
    *,
    document: models.StatusTableDocument | None = None,
    headers: Iterable[str] = (),
    rows: Iterable[Iterable[str]] = (),
) -> models.StatusTableDocument:
    if document is not None:
        return _document_for_kind(status_kind, document)
    output_headers, output_rows = _materialize_table_data(headers, rows)
    data = models.StatusTableData(headers=output_headers, rows=output_rows)
    locked = SCENE_DEFAULT_LOCKED_KEYS if status_kind == models.STATUS_KIND_SCENE else set()
    return models.StatusTableDocument.from_data(data, locked_keys=locked)


def _updated_document(
    current: models.StatusTableDocument,
    status_kind: str,
    *,
    document: models.StatusTableDocument | None,
    headers: Iterable[str] | None,
    rows: Iterable[Iterable[str]] | None,
) -> models.StatusTableDocument:
    if document is not None:
        return _document_for_kind(status_kind, document)
    if headers is None and rows is None:
        return _document_for_kind(status_kind, current)
    output_headers = current.headers if headers is None else tuple(str(item) for item in headers)
    output_rows = current.data_rows if rows is None else tuple(tuple(str(cell) for cell in row) for row in rows)
    return _document_for_kind(status_kind, current.with_data(models.StatusTableData(output_headers, output_rows)))


def _document_for_kind(status_kind: str, document: models.StatusTableDocument) -> models.StatusTableDocument:
    kind = models.validate_status_kind(status_kind)
    if kind != models.STATUS_KIND_SCENE:
        return document.validated()
    rows = tuple(
        models.StatusTableRow(
            row.key,
            row.value,
            row.runtime_key_locked or row.key in SCENE_DEFAULT_LOCKED_KEYS,
            dict(row.metadata),
        )
        for row in document.rows
    )
    return models.StatusTableDocument(
        schema_version=document.schema_version,
        kind=document.kind,
        mode=document.mode,
        key_column=document.key_column,
        value_column=document.value_column,
        rows=rows,
        metadata=dict(document.metadata),
    ).validated()


def _materialize_table_data(
    headers: Iterable[str],
    rows: Iterable[Iterable[str]],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    return (
        tuple(str(item) for item in headers),
        tuple(tuple(str(cell) for cell in row) for row in rows),
    )


def _materialize_row_values(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        return (str(values),)
    return tuple(str(item) for item in values)


def _rows_to_attrs(rows: Iterable[Iterable[str]]) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for row in rows:
        cells = tuple(row)
        if not cells:
            continue
        attrs[str(cells[0])] = str(cells[1]) if len(cells) > 1 else ""
    return attrs


def _validate_name(name: str, label: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label} name must not be empty")
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"{label} name must not contain path separators: {name!r}")
