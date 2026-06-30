"""Status table service backed by SQL indexes and JSON content files."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from peewee import Database, DoesNotExist, IntegrityError, SQL

from rpg_data import models
from rpg_data.repositories.records import (
    SessionRecord,
    SessionStatusTableRecord,
    SessionStatusTypeRecord,
    StatusTableTemplateRecord,
    StatusTypeRecord,
    StoryRecord,
    StoryStatusTableRecord,
    WorkspaceRecord,
    bind_database,
)
from rpg_data.settings import resolve_workspace_relative_path, resolve_workspace_root

__all__ = ["StatusTableService"]

logger = logging.getLogger("rpg_data.status")

SCENE_BUILTIN_KEY = "scene"
SCENE_DEFAULT_HEADERS = (models.STATUS_KEY_COLUMN, models.STATUS_VALUE_COLUMN)
SCENE_DEFAULT_LOCKED_KEYS = {"时间", "位置", "在场人物"}
_TEMPLATE_STATUS_DIR = "template_status"
_SESSION_STORIES_DIR = "stories"
_SESSION_STATUS_DIR = "status"
_STATUS_FILE_SUFFIX = ".status.json"
_STATUS_TABLE_KIND = "status_table"
_STATUS_TABLE_MODE = "key_value"


class StatusTableService:
    """Manage status table indexes in SQL and table content in JSON files."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        logger.debug("status table service initialized database=%s", database)

    # ------------------------------------------------------------------
    # Template type CRUD
    # ------------------------------------------------------------------

    def list_types(self, workspace_id: str) -> list[models.StatusType]:
        rows = (
            StatusTypeRecord
            .select()
            .where(StatusTypeRecord.workspace == workspace_id)
            .order_by(StatusTypeRecord.sort_order, StatusTypeRecord.id)
        )
        result = [_to_status_type(row) for row in rows]
        logger.debug("listed status types workspace_id=%s count=%s", workspace_id, len(result))
        return result

    def create_type(
        self,
        workspace_id: str,
        name: str,
        *,
        builtin_key: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StatusType:
        _validate_name(name, "status type")
        self._workspace_root(workspace_id)
        builtin_key = str(builtin_key or "")
        if builtin_key and self._find_builtin_type(workspace_id, builtin_key) is not None:
            raise ValueError(f"Status builtin type already exists: {builtin_key}")
        try:
            row = StatusTypeRecord.create(
                workspace=workspace_id,
                name=name,
                builtin_key=builtin_key,
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
        except IntegrityError as exc:
            logger.warning("status type create conflict workspace_id=%s name=%s", workspace_id, name)
            raise ValueError(f"Status type already exists: {name}") from exc
        logger.info(
            "created status type type_id=%s workspace_id=%s name=%s builtin_key=%s",
            row.id,
            workspace_id,
            name,
            builtin_key,
        )
        return _to_status_type(row)

    def rename_type(self, type_id: int, new_name: str) -> models.StatusType:
        _validate_name(new_name, "status type")
        row = self._get_type_row(type_id)
        old_name = str(row.name)
        if old_name == new_name:
            return _to_status_type(row)

        workspace_root = self._workspace_root(str(row.workspace_id))
        templates = list(
            StatusTableTemplateRecord
            .select()
            .where(StatusTableTemplateRecord.status_type == row.id)
        )
        moves = [
            (
                resolve_workspace_relative_path(workspace_root, template.relative_path),
                resolve_workspace_relative_path(
                    workspace_root,
                    _template_relative_path(new_name, str(template.name)),
                ),
                template,
            )
            for template in templates
        ]
        for old_path, new_path, _template in moves:
            if old_path != new_path and new_path.exists():
                raise FileExistsError(str(new_path))

        moved: list[tuple[Path, Path]] = []
        rewritten: list[tuple[Path, dict[str, Any]]] = []
        try:
            for old_path, new_path, _template in moves:
                if old_path == new_path:
                    continue
                if not old_path.is_file():
                    raise FileNotFoundError(str(old_path))
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                moved.append((old_path, new_path))
            for old_path, new_path, _template in moves:
                target_path = new_path if old_path != new_path else old_path
                document = _read_status_document(target_path)
                rewritten.append((target_path, dict(document)))
                document["typeName"] = new_name
                document["builtinKey"] = str(row.builtin_key or "")
                _write_status_document(target_path, document)
            with self._database.atomic():
                row.name = new_name
                row.updated_at = SQL("CURRENT_TIMESTAMP")
                row.save()
                for _old_path, _new_path, template in moves:
                    template.relative_path = _template_relative_path(new_name, str(template.name))
                    template.updated_at = SQL("CURRENT_TIMESTAMP")
                    template.save()
        except Exception:
            for path, document in reversed(rewritten):
                if path.exists():
                    _write_status_document(path, document)
            for old_path, new_path in reversed(moved):
                if new_path.exists() and not old_path.exists():
                    old_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(new_path), str(old_path))
            raise

        _remove_empty_parents(
            resolve_workspace_relative_path(workspace_root, _template_type_relative_path(old_name)),
            resolve_workspace_relative_path(workspace_root, _TEMPLATE_STATUS_DIR),
        )
        logger.info(
            "renamed status type type_id=%s old_name=%s new_name=%s moved_files=%s",
            type_id,
            old_name,
            new_name,
            len(moved),
        )
        return _to_status_type(self._get_type_row(type_id))

    def delete_type(self, type_id: int) -> None:
        row = self._get_type_row(type_id)
        workspace_root = self._workspace_root(str(row.workspace_id))
        template_paths = [
            resolve_workspace_relative_path(workspace_root, template.relative_path)
            for template in StatusTableTemplateRecord.select().where(
                StatusTableTemplateRecord.status_type == row.id
            )
        ]
        with self._database.atomic():
            row.delete_instance(recursive=True)
        for path in template_paths:
            _unlink_missing_ok(path)
        _remove_empty_parents(
            resolve_workspace_relative_path(workspace_root, _template_type_relative_path(str(row.name))),
            resolve_workspace_relative_path(workspace_root, _TEMPLATE_STATUS_DIR),
        )
        logger.info(
            "deleted status type type_id=%s workspace_id=%s name=%s template_files=%s",
            type_id,
            row.workspace_id,
            row.name,
            len(template_paths),
        )

    # ------------------------------------------------------------------
    # Template table CRUD
    # ------------------------------------------------------------------

    def list_templates(
        self,
        workspace_id: str,
        *,
        type_name: str | None = None,
    ) -> list[models.StatusTableTemplate]:
        query = (
            StatusTableTemplateRecord
            .select(StatusTableTemplateRecord, StatusTypeRecord)
            .join(StatusTypeRecord)
            .where(StatusTableTemplateRecord.workspace == workspace_id)
        )
        if type_name is not None:
            query = query.where(StatusTypeRecord.name == type_name)
        query = query.order_by(
            StatusTypeRecord.sort_order,
            StatusTypeRecord.id,
            StatusTableTemplateRecord.sort_order,
            StatusTableTemplateRecord.id,
        )
        workspace_root = self._workspace_root(workspace_id)
        result = [_to_template(row, workspace_root) for row in query]
        logger.debug(
            "listed status templates workspace_id=%s type_name=%s count=%s",
            workspace_id,
            type_name,
            len(result),
        )
        return result

    def get_template(self, template_id: int) -> models.StatusTableTemplate | None:
        row = (
            StatusTableTemplateRecord
            .select(StatusTableTemplateRecord, StatusTypeRecord)
            .join(StatusTypeRecord)
            .where(StatusTableTemplateRecord.id == template_id)
            .first()
        )
        if row is None:
            logger.debug("status template not found template_id=%s", template_id)
            return None
        template = _to_template(row, self._workspace_root(str(row.workspace_id)))
        logger.debug(
            "loaded status template template_id=%s workspace_id=%s name=%s",
            template_id,
            template.workspace_id,
            template.name,
        )
        return template

    def create_template(
        self,
        workspace_id: str,
        type_name: str,
        name: str,
        *,
        headers: Iterable[str] = (),
        rows: Iterable[Iterable[str]] = (),
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StatusTableTemplate:
        _validate_name(type_name, "status type")
        _validate_name(name, "status table")
        type_row = self._get_type_by_name(workspace_id, type_name)
        workspace_root = self._workspace_root(workspace_id)
        relative_path = _template_relative_path(type_name, name)
        path = resolve_workspace_relative_path(workspace_root, relative_path)
        if path.exists():
            raise FileExistsError(str(path))

        output_headers, output_rows = _materialize_table_data(headers, rows)
        _write_status_json(
            path,
            type_name=type_name,
            name=name,
            builtin_key=str(type_row.builtin_key or ""),
            description=description,
            headers=output_headers,
            rows=output_rows,
            metadata_json=metadata_json,
        )
        try:
            with self._database.atomic():
                row = StatusTableTemplateRecord.create(
                    workspace=workspace_id,
                    status_type=type_row.id,
                    name=name,
                    relative_path=relative_path,
                    description=description,
                    sort_order=sort_order,
                    metadata_json=metadata_json,
                )
        except Exception:
            _unlink_missing_ok(path)
            raise
        logger.info(
            "created status template template_id=%s workspace_id=%s type_name=%s "
            "name=%s relative_path=%s headers=%s rows=%s",
            row.id,
            workspace_id,
            type_name,
            name,
            relative_path,
            output_headers,
            output_rows,
        )
        return _to_template(row, workspace_root)

    def update_template(
        self,
        template_id: int,
        *,
        type_name: str | None = None,
        name: str | None = None,
        headers: Iterable[str] | None = None,
        rows: Iterable[Iterable[str]] | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> models.StatusTableTemplate:
        row = self._get_template_row(template_id)
        workspace_id = str(row.workspace_id)
        workspace_root = self._workspace_root(workspace_id)
        current_type = row.status_type
        target_type = current_type if type_name is None else self._get_type_by_name(workspace_id, type_name)
        target_name = str(row.name) if name is None else name
        _validate_name(target_name, "status table")

        old_relative_path = str(row.relative_path)
        old_path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        new_relative_path = _template_relative_path(str(target_type.name), target_name)
        new_path = resolve_workspace_relative_path(workspace_root, new_relative_path)
        current_headers, current_rows = _read_status_json(old_path)
        output_headers = current_headers if headers is None else tuple(str(item) for item in headers)
        output_rows = current_rows if rows is None else tuple(tuple(str(cell) for cell in item) for item in rows)
        path_changed = old_path != new_path
        if path_changed and new_path.exists():
            raise FileExistsError(str(new_path))

        moved = False
        try:
            if path_changed:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                moved = True
            output_description = str(row.description or "") if description is None else description
            _write_status_json(
                new_path,
                type_name=str(target_type.name),
                name=target_name,
                builtin_key=str(target_type.builtin_key or ""),
                description=output_description,
                headers=output_headers,
                rows=output_rows,
                metadata_json=str(row.metadata_json or "{}"),
            )
            with self._database.atomic():
                row.status_type = target_type.id
                row.name = target_name
                row.relative_path = new_relative_path
                if description is not None:
                    row.description = description
                if sort_order is not None:
                    row.sort_order = sort_order
                row.updated_at = SQL("CURRENT_TIMESTAMP")
                row.save()
        except Exception:
            if moved and new_path.exists() and not old_path.exists():
                old_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(new_path), str(old_path))
            raise
        logger.info(
            "updated status template template_id=%s old_relative_path=%s "
            "new_relative_path=%s path_changed=%s headers=%s rows=%s",
            template_id,
            old_relative_path,
            new_relative_path,
            path_changed,
            output_headers,
            output_rows,
        )
        return _to_template(self._get_template_row(template_id), workspace_root)

    def delete_template(self, template_id: int) -> None:
        row = self._get_template_row(template_id)
        workspace_root = self._workspace_root(str(row.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        with self._database.atomic():
            row.delete_instance(recursive=True)
        _unlink_missing_ok(path)
        _remove_empty_parents(path.parent, resolve_workspace_relative_path(workspace_root, _TEMPLATE_STATUS_DIR))
        logger.info(
            "deleted status template template_id=%s workspace_id=%s relative_path=%s",
            template_id,
            row.workspace_id,
            row.relative_path,
        )

    # ------------------------------------------------------------------
    # Story mounts
    # ------------------------------------------------------------------

    def list_story_mounts(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryStatusTable]:
        query = (
            StoryStatusTableRecord
            .select(StoryStatusTableRecord, StatusTableTemplateRecord, StatusTypeRecord)
            .join(StatusTableTemplateRecord)
            .join(StatusTypeRecord)
            .where(
                (StoryStatusTableRecord.workspace == workspace_id)
                & (StoryStatusTableRecord.story == story_id)
            )
            .order_by(StoryStatusTableRecord.sort_order, StoryStatusTableRecord.id)
        )
        result = [_to_story_mount(row) for row in query]
        logger.debug(
            "listed story status mounts workspace_id=%s story_id=%s count=%s",
            workspace_id,
            story_id,
            len(result),
        )
        return result

    def mount_template(
        self,
        workspace_id: str,
        story_id: int,
        template_id: int,
        *,
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.StoryStatusTable:
        story = self._get_story_row(story_id)
        if str(story.workspace_id) != workspace_id:
            raise FileNotFoundError(f"Story not found in workspace: {workspace_id}/{story_id}")
        template = self._get_template_row(template_id)
        if str(template.workspace_id) != workspace_id:
            raise FileNotFoundError(f"Status template not found in workspace: {workspace_id}/{template_id}")
        try:
            row = StoryStatusTableRecord.create(
                workspace=workspace_id,
                story=story_id,
                status_table=template_id,
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
        except IntegrityError as exc:
            logger.warning(
                "status template mount conflict workspace_id=%s story_id=%s template_id=%s",
                workspace_id,
                story_id,
                template_id,
            )
            raise ValueError(f"Status table already mounted to story: {story_id}/{template_id}") from exc
        logger.info(
            "mounted status template mount_id=%s workspace_id=%s story_id=%s template_id=%s",
            row.id,
            workspace_id,
            story_id,
            template_id,
        )
        return _to_story_mount(self._get_story_mount_row(int(row.id)))

    def unmount_template(self, mount_id: int) -> None:
        row = self._get_story_mount_row(mount_id)
        row.delete_instance()
        logger.info(
            "unmounted status template mount_id=%s workspace_id=%s story_id=%s template_id=%s",
            mount_id,
            row.workspace_id,
            row.story_id,
            row.status_table_id,
        )

    # ------------------------------------------------------------------
    # Session copies
    # ------------------------------------------------------------------

    def initialize_session_tables(self, session_id: str) -> list[models.SessionStatusTable]:
        session = self._get_session_row(session_id)
        if SessionStatusTableRecord.select().where(SessionStatusTableRecord.session == session_id).exists():
            tables = self.list_tables(session_id)
            logger.debug(
                "session status tables already initialized session_id=%s table_count=%s",
                session_id,
                len(tables),
            )
            return tables

        workspace_id = str(session.workspace_id)
        story_id = int(session.story_id)
        logger.info(
            "initializing session status tables session_id=%s workspace_id=%s story_id=%s",
            session_id,
            workspace_id,
            story_id,
        )
        workspace_root = self._workspace_root(workspace_id)
        created_files: list[Path] = []
        type_map: dict[int, SessionStatusTypeRecord] = {}

        mounts = list(
            StoryStatusTableRecord
            .select(StoryStatusTableRecord, StatusTableTemplateRecord, StatusTypeRecord)
            .join(StatusTableTemplateRecord)
            .join(StatusTypeRecord)
            .where(
                (StoryStatusTableRecord.workspace == workspace_id)
                & (StoryStatusTableRecord.story == story_id)
            )
            .order_by(StoryStatusTableRecord.sort_order, StoryStatusTableRecord.id)
        )
        logger.debug("found mounted status templates session_id=%s mount_count=%s", session_id, len(mounts))
        try:
            with self._database.atomic():
                for mount in mounts:
                    template = mount.status_table
                    type_row = template.status_type
                    source_path = resolve_workspace_relative_path(workspace_root, template.relative_path)
                    if not source_path.is_file():
                        logger.warning(
                            "skip missing mounted status template session_id=%s template_id=%s relative_path=%s",
                            session_id,
                            template.id,
                            template.relative_path,
                        )
                        continue
                    session_type = type_map.get(int(type_row.id))
                    if session_type is None:
                        session_type = SessionStatusTypeRecord.create(
                            session=session_id,
                            workspace=workspace_id,
                            story=story_id,
                            source_type_id=int(type_row.id),
                            name=str(type_row.name),
                            builtin_key=str(type_row.builtin_key or ""),
                            sort_order=int(type_row.sort_order),
                            metadata_json=str(type_row.metadata_json or "{}"),
                        )
                        type_map[int(type_row.id)] = session_type

                    relative_path = _session_relative_path(story_id, session_id, str(type_row.name), str(template.name))
                    target_path = resolve_workspace_relative_path(workspace_root, relative_path)
                    if target_path.exists():
                        raise FileExistsError(str(target_path))
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, target_path)
                    created_files.append(target_path)
                    SessionStatusTableRecord.create(
                        session=session_id,
                        session_type=session_type.id,
                        source_table_id=int(template.id),
                        name=str(template.name),
                        relative_path=relative_path,
                        description=str(template.description or ""),
                        sort_order=int(mount.sort_order),
                        metadata_json=str(template.metadata_json or "{}"),
                    )
        except Exception:
            logger.exception(
                "failed to initialize session status tables session_id=%s created_files=%s",
                session_id,
                len(created_files),
            )
            for path in reversed(created_files):
                _unlink_missing_ok(path)
                _remove_empty_parents(
                    path.parent,
                    resolve_workspace_relative_path(workspace_root, _session_root_relative_path(story_id, session_id)),
                )
            raise
        tables = self.list_tables(session_id)
        logger.info(
            "initialized session status tables session_id=%s type_count=%s table_count=%s copied_files=%s",
            session_id,
            len(type_map),
            len(tables),
            len(created_files),
        )
        return tables

    def list_session_types(self, session_id: str) -> list[models.SessionStatusType]:
        rows = (
            SessionStatusTypeRecord
            .select()
            .where(SessionStatusTypeRecord.session == session_id)
            .order_by(SessionStatusTypeRecord.sort_order, SessionStatusTypeRecord.id)
        )
        result = [_to_session_type(row) for row in rows]
        logger.debug("listed session status types session_id=%s count=%s", session_id, len(result))
        return result

    def create_session_type(
        self,
        session_id: str,
        name: str,
        *,
        builtin_key: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.SessionStatusType:
        _validate_name(name, "session status type")
        session = self._get_session_row(session_id)
        try:
            row = SessionStatusTypeRecord.create(
                session=session_id,
                workspace=str(session.workspace_id),
                story=int(session.story_id),
                source_type_id=None,
                name=name,
                builtin_key=str(builtin_key or ""),
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
        except IntegrityError as exc:
            logger.warning("session status type create conflict session_id=%s name=%s", session_id, name)
            raise ValueError(f"Session status type already exists: {name}") from exc
        logger.info(
            "created session status type session_type_id=%s session_id=%s name=%s builtin_key=%s",
            row.id,
            session_id,
            name,
            builtin_key,
        )
        return _to_session_type(row)

    def list_tables(
        self,
        session_id: str,
        type_name: str | None = None,
        *,
        include_scene: bool = True,
    ) -> list[models.SessionStatusTable]:
        query = (
            SessionStatusTableRecord
            .select(SessionStatusTableRecord, SessionStatusTypeRecord)
            .join(SessionStatusTypeRecord)
            .where(SessionStatusTableRecord.session == session_id)
        )
        if type_name is not None:
            query = query.where(SessionStatusTypeRecord.name == type_name)
        if not include_scene:
            query = query.where(SessionStatusTypeRecord.builtin_key != SCENE_BUILTIN_KEY)
        query = query.order_by(
            SessionStatusTypeRecord.sort_order,
            SessionStatusTypeRecord.id,
            SessionStatusTableRecord.sort_order,
            SessionStatusTableRecord.id,
        )
        result = [
            _to_session_table(row, self._workspace_root(str(row.session_type.workspace_id)))
            for row in query
        ]
        logger.debug(
            "listed session status tables session_id=%s type_name=%s include_scene=%s count=%s",
            session_id,
            type_name,
            include_scene,
            len(result),
        )
        return result

    def list_context_tables(self, session_id: str) -> list[models.SessionStatusTable]:
        tables: list[models.SessionStatusTable] = []
        query = (
            SessionStatusTableRecord
            .select(SessionStatusTableRecord, SessionStatusTypeRecord)
            .join(SessionStatusTypeRecord)
            .where(
                (SessionStatusTableRecord.session == session_id)
                & (SessionStatusTypeRecord.builtin_key != SCENE_BUILTIN_KEY)
            )
            .order_by(
                SessionStatusTypeRecord.sort_order,
                SessionStatusTypeRecord.id,
                SessionStatusTableRecord.sort_order,
                SessionStatusTableRecord.id,
            )
        )
        for row in query:
            try:
                tables.append(_to_session_table(row, self._workspace_root(str(row.session_type.workspace_id))))
            except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
                logger.debug("skip unavailable status table JSON for context: %s", exc)
        logger.debug("listed context status tables session_id=%s count=%s", session_id, len(tables))
        return tables

    def get_table(
        self,
        session_id: str,
        type_name: str,
        table_name: str,
    ) -> models.SessionStatusTable:
        row = self._find_session_table(session_id, type_name, table_name)
        if row is None:
            raise FileNotFoundError(f"Status table not found: {type_name}/{table_name}")
        table = _to_session_table(row, self._workspace_root(str(row.session_type.workspace_id)))
        logger.debug(
            "loaded status table session_id=%s type_name=%s table_name=%s table_id=%s",
            session_id,
            type_name,
            table_name,
            table.id,
        )
        return table

    def get_table_by_id(self, table_id: int) -> models.SessionStatusTable:
        row = self._get_session_table_row(table_id)
        table = _to_session_table(row, self._workspace_root(str(row.session_type.workspace_id)))
        logger.debug(
            "loaded status table by id table_id=%s session_id=%s name=%s",
            table_id,
            table.session_id,
            table.name,
        )
        return table

    def create_table(
        self,
        session_id: str,
        type_name: str,
        table_name: str,
        headers: Iterable[str] = (),
        rows: Iterable[Iterable[str]] = (),
        *,
        description: str = "",
        sort_order: int = 0,
        metadata_json: str = "{}",
    ) -> models.SessionStatusTable:
        _validate_name(type_name, "session status type")
        _validate_name(table_name, "session status table")
        session_type = self._get_session_type_by_name(session_id, type_name)
        workspace_root = self._workspace_root(str(session_type.workspace_id))
        relative_path = _session_relative_path(
            int(session_type.story_id),
            session_id,
            type_name,
            table_name,
        )
        path = resolve_workspace_relative_path(workspace_root, relative_path)
        if path.exists():
            raise FileExistsError(str(path))

        output_headers, output_rows = _materialize_table_data(headers, rows)
        _write_status_json(
            path,
            type_name=type_name,
            name=table_name,
            builtin_key=str(session_type.builtin_key or ""),
            description=description,
            headers=output_headers,
            rows=output_rows,
            metadata_json=metadata_json,
        )
        try:
            row = SessionStatusTableRecord.create(
                session=session_id,
                session_type=session_type.id,
                source_table_id=None,
                name=table_name,
                relative_path=relative_path,
                description=description,
                sort_order=sort_order,
                metadata_json=metadata_json,
            )
        except Exception:
            _unlink_missing_ok(path)
            raise
        logger.info(
            "created session status table table_id=%s session_id=%s type_name=%s "
            "table_name=%s relative_path=%s headers=%s rows=%s",
            row.id,
            session_id,
            type_name,
            table_name,
            relative_path,
            output_headers,
            output_rows,
        )
        return _to_session_table(row, workspace_root)

    def save_table(
        self,
        session_id: str,
        type_name: str,
        table_name: str,
        headers: Iterable[str],
        rows: Iterable[Iterable[str]],
    ) -> models.SessionStatusTable:
        row = self._find_session_table(session_id, type_name, table_name)
        if row is None:
            raise FileNotFoundError(f"Status table not found: {type_name}/{table_name}")
        workspace_root = self._workspace_root(str(row.session_type.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        output_headers, output_rows = _materialize_table_data(headers, rows)
        _write_status_json(
            path,
            type_name=str(row.session_type.name),
            name=str(row.name),
            builtin_key=str(row.session_type.builtin_key or ""),
            description=str(row.description or ""),
            headers=output_headers,
            rows=output_rows,
            metadata_json=str(row.metadata_json or "{}"),
        )
        _touch(SessionStatusTableRecord, int(row.id))
        logger.info(
            "saved session status table table_id=%s session_id=%s type_name=%s "
            "table_name=%s headers=%s rows=%s",
            row.id,
            session_id,
            type_name,
            table_name,
            output_headers,
            output_rows,
        )
        return self.get_table(session_id, type_name, table_name)

    def set_cell(
        self,
        table_id: int,
        row: int | models.StatusRowRef,
        column: int | str,
        value: str,
    ) -> models.SessionStatusTable:
        logger.info(
            "updating status table cell table_id=%s row_ref=%s column=%s value=%s",
            table_id,
            row,
            column,
            value,
        )
        return self._update_table_data(
            table_id,
            lambda data: data.with_cell(row, column, value),
        )

    def append_row(
        self,
        table_id: int,
        values: Iterable[str],
    ) -> models.SessionStatusTable:
        row_values = _materialize_row_values(values)
        logger.info("appending status table row table_id=%s values=%s", table_id, row_values)
        return self._update_table_data(
            table_id,
            lambda data: data.with_appended_row(row_values),
        )

    def replace_row(
        self,
        table_id: int,
        row: int | models.StatusRowRef,
        values: Iterable[str],
    ) -> models.SessionStatusTable:
        row_values = _materialize_row_values(values)
        logger.info("replacing status table row table_id=%s row_ref=%s values=%s", table_id, row, row_values)
        return self._update_table_data(
            table_id,
            lambda data: data.with_replaced_row(row, row_values),
        )

    def delete_row(
        self,
        table_id: int,
        row: int | models.StatusRowRef,
    ) -> models.SessionStatusTable:
        logger.info("deleting status table row table_id=%s row_ref=%s", table_id, row)
        return self._update_table_data(
            table_id,
            lambda data: data.with_deleted_row(row),
        )

    def set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = models.STATUS_KEY_COLUMN,
        value_column: int | str = models.STATUS_VALUE_COLUMN,
    ) -> models.SessionStatusTable:
        logger.info(
            "setting status table key/value table_id=%s key=%s value=%s key_column=%s value_column=%s",
            table_id,
            key,
            value,
            key_column,
            value_column,
        )
        return self._update_table_data(
            table_id,
            lambda data: data.with_key_value(
                key,
                value,
                key_column=key_column,
                value_column=value_column,
            ),
        )

    def delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = models.STATUS_KEY_COLUMN,
    ) -> models.SessionStatusTable:
        logger.info(
            "deleting status table key/value table_id=%s key=%s key_column=%s",
            table_id,
            key,
            key_column,
        )
        return self._update_table_data(
            table_id,
            lambda data: data.without_key(key, key_column=key_column),
        )

    def runtime_set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = models.STATUS_KEY_COLUMN,
        value_column: int | str = models.STATUS_VALUE_COLUMN,
    ) -> models.SessionStatusTable:
        """Set a key/value pair from LLM runtime.

        Runtime locks protect the key identity, not the value, so updating any
        existing key's value remains allowed. Newly created rows are unlocked.
        """

        return self.set_key_value(
            table_id,
            key,
            value,
            key_column=key_column,
            value_column=value_column,
        )

    def runtime_delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = models.STATUS_KEY_COLUMN,
    ) -> models.SessionStatusTable:
        if self._runtime_key_locked(table_id, key):
            raise PermissionError(f"Status key is runtime locked: {key}")
        return self.delete_key_value(table_id, key, key_column=key_column)

    def rename_table(
        self,
        session_id: str,
        type_name: str,
        old_name: str,
        new_name: str,
    ) -> models.SessionStatusTable:
        _validate_name(new_name, "session status table")
        row = self._find_session_table(session_id, type_name, old_name)
        if row is None:
            raise FileNotFoundError(f"Status table not found: {type_name}/{old_name}")
        if old_name == new_name:
            return _to_session_table(row, self._workspace_root(str(row.session_type.workspace_id)))
        workspace_root = self._workspace_root(str(row.session_type.workspace_id))
        old_path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        new_relative_path = _session_relative_path(
            int(row.session_type.story_id),
            session_id,
            type_name,
            new_name,
        )
        new_path = resolve_workspace_relative_path(workspace_root, new_relative_path)
        if new_path.exists():
            raise FileExistsError(str(new_path))
        if not old_path.is_file():
            raise FileNotFoundError(str(old_path))

        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        try:
            headers, rows = _read_status_json(new_path)
            _write_status_json(
                new_path,
                type_name=type_name,
                name=new_name,
                builtin_key=str(row.session_type.builtin_key or ""),
                description=str(row.description or ""),
                headers=headers,
                rows=rows,
                metadata_json=str(row.metadata_json or "{}"),
            )
            with self._database.atomic():
                row.name = new_name
                row.relative_path = new_relative_path
                row.updated_at = SQL("CURRENT_TIMESTAMP")
                row.save()
        except Exception:
            if new_path.exists() and not old_path.exists():
                old_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(new_path), str(old_path))
            raise
        logger.info(
            "renamed session status table session_id=%s type_name=%s old_name=%s new_name=%s relative_path=%s",
            session_id,
            type_name,
            old_name,
            new_name,
            new_relative_path,
        )
        return self.get_table(session_id, type_name, new_name)

    def delete_table(self, session_id: str, type_name: str, table_name: str) -> None:
        row = self._find_session_table(session_id, type_name, table_name)
        if row is None:
            raise FileNotFoundError(f"Status table not found: {type_name}/{table_name}")
        workspace_root = self._workspace_root(str(row.session_type.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        with self._database.atomic():
            row.delete_instance()
        _unlink_missing_ok(path)
        _remove_empty_parents(
            path.parent,
            resolve_workspace_relative_path(
                workspace_root,
                _session_root_relative_path(int(row.session_type.story_id), session_id),
            ),
        )
        logger.info(
            "deleted session status table table_id=%s session_id=%s type_name=%s table_name=%s",
            row.id,
            session_id,
            type_name,
            table_name,
        )

    def clear_unindexed_session_files(self, session_id: str) -> list[str]:
        """Delete session status JSON files that are not referenced by SQL indexes.

        SQL remains the complete index for status tables. This cleanup only scans
        the current session's status copy directory and removes orphan
        ``.status.json`` files under it; indexed files and non-status files are
        left untouched.
        Returned paths are relative to the workspace root.
        """

        session = self._get_session_row(session_id)
        workspace_root = self._workspace_root(str(session.workspace_id))
        status_root = resolve_workspace_relative_path(
            workspace_root,
            _session_status_root_relative_path(int(session.story_id), session_id),
        )
        if not status_root.is_dir():
            logger.debug(
                "skip unindexed status json cleanup missing directory session_id=%s root=%s",
                session_id,
                status_root,
            )
            return []

        indexed_paths = {
            resolve_workspace_relative_path(workspace_root, row.relative_path).resolve()
            for row in SessionStatusTableRecord
            .select(SessionStatusTableRecord.relative_path)
            .where(SessionStatusTableRecord.session == session_id)
        }
        removed: list[str] = []
        workspace_root_resolved = workspace_root.resolve()
        for path in sorted(status_root.rglob(f"*{_STATUS_FILE_SUFFIX}")):
            resolved = path.resolve()
            if resolved in indexed_paths:
                continue
            _unlink_missing_ok(path)
            removed.append(resolved.relative_to(workspace_root_resolved).as_posix())
            _remove_empty_parents(path.parent, status_root)
        if removed:
            logger.info(
                "removed unindexed session status files session_id=%s count=%s paths=%s",
                session_id,
                len(removed),
                removed,
            )
        else:
            logger.debug("no unindexed session status files session_id=%s", session_id)
        return removed

    # ------------------------------------------------------------------
    # Scene helpers
    # ------------------------------------------------------------------

    def get_active_scene_table(self, session_id: str) -> models.SessionStatusTable | None:
        row = (
            SessionStatusTableRecord
            .select(SessionStatusTableRecord, SessionStatusTypeRecord)
            .join(SessionStatusTypeRecord)
            .where(
                (SessionStatusTableRecord.session == session_id)
                & (SessionStatusTypeRecord.builtin_key == SCENE_BUILTIN_KEY)
            )
            .order_by(SessionStatusTableRecord.sort_order, SessionStatusTableRecord.id)
            .first()
        )
        if row is None:
            logger.debug("active scene table not found session_id=%s", session_id)
            return None
        table = _to_session_table(row, self._workspace_root(str(row.session_type.workspace_id)))
        logger.debug("loaded active scene table session_id=%s table_id=%s name=%s", session_id, table.id, table.name)
        return table

    def get_scene_attrs(self, session_id: str) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            logger.debug("scene attrs unavailable session_id=%s", session_id)
            return None
        attrs = _rows_to_attrs(table.rows)
        logger.debug("loaded scene attrs session_id=%s attr_count=%s attrs=%s", session_id, len(attrs), attrs)
        return attrs

    def replace_scene_attrs(
        self,
        session_id: str,
        attrs: Mapping[str, str],
    ) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            logger.debug("replace scene attrs skipped missing scene session_id=%s", session_id)
            return None
        clean_attrs = {str(key): str(value) for key, value in attrs.items()}
        updated = self._replace_table_data(
            table.id,
            models.StatusTableData(
                headers=SCENE_DEFAULT_HEADERS,
                rows=tuple((key, value) for key, value in clean_attrs.items()),
            ),
        )
        logger.info(
            "replaced scene attrs session_id=%s table_id=%s attr_count=%s attrs=%s",
            session_id,
            table.id,
            len(clean_attrs),
            clean_attrs,
        )
        return _rows_to_attrs(updated.rows)

    def set_scene_attr(self, session_id: str, key: str, value: str) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            logger.debug("set scene attr skipped missing scene session_id=%s key=%s", session_id, key)
            return None
        updated = self.runtime_set_key_value(table.id, str(key), str(value))
        logger.info(
            "set scene attr session_id=%s table_id=%s key=%s value=%s updated_attrs=%s",
            session_id,
            table.id,
            key,
            value,
            _rows_to_attrs(updated.rows),
        )
        return _rows_to_attrs(updated.rows)

    def delete_scene_attr(self, session_id: str, key: str) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            logger.debug("delete scene attr skipped missing scene session_id=%s key=%s", session_id, key)
            return None
        try:
            table = self.runtime_delete_key_value(table.id, str(key))
            logger.info(
                "deleted scene attr session_id=%s table_id=%s key=%s updated_attrs=%s",
                session_id,
                table.id,
                key,
                _rows_to_attrs(table.rows),
            )
        except FileNotFoundError:
            logger.debug("delete scene attr skipped missing key session_id=%s key=%s", session_id, key)
        except PermissionError:
            logger.debug("delete scene attr skipped runtime locked key session_id=%s key=%s", session_id, key)
        return _rows_to_attrs(table.rows)

    # ------------------------------------------------------------------
    # Internal lookups
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
        workspace_root = self._workspace_root(str(row.session_type.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        _write_status_json(
            path,
            type_name=str(row.session_type.name),
            name=str(row.name),
            builtin_key=str(row.session_type.builtin_key or ""),
            description=str(row.description or ""),
            headers=data.headers,
            rows=data.rows,
            metadata_json=str(row.metadata_json or "{}"),
        )
        _touch(SessionStatusTableRecord, int(row.id))
        logger.info(
            "wrote session status json table_id=%s session_id=%s relative_path=%s "
            "header_count=%s row_count=%s headers=%s rows=%s",
            table_id,
            row.session_id,
            row.relative_path,
            len(data.headers),
            len(data.rows),
            data.headers,
            data.rows,
        )
        return self.get_table_by_id(table_id)

    def _runtime_key_locked(self, table_id: int, key: str) -> bool:
        row = self._get_session_table_row(table_id)
        workspace_root = self._workspace_root(str(row.session_type.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        document = _read_status_document(path)
        expected = str(key)
        for item in _iter_status_rows(document):
            if str(item.get("key", "")) == expected:
                return bool(item.get("runtimeKeyLocked", False))
        raise FileNotFoundError(f"Status table key not found: {key}")

    def _workspace_root(self, workspace_id: str) -> Path:
        try:
            row = WorkspaceRecord.get_by_id(workspace_id)
        except DoesNotExist as exc:
            raise FileNotFoundError(f"Workspace not found: {workspace_id}") from exc
        return resolve_workspace_root(str(row.root_path))

    def _find_builtin_type(self, workspace_id: str, builtin_key: str) -> StatusTypeRecord | None:
        return (
            StatusTypeRecord
            .select()
            .where(
                (StatusTypeRecord.workspace == workspace_id)
                & (StatusTypeRecord.builtin_key == builtin_key)
            )
            .first()
        )

    def _get_type_row(self, type_id: int) -> StatusTypeRecord:
        try:
            return StatusTypeRecord.get_by_id(type_id)
        except DoesNotExist as exc:
            raise FileNotFoundError(f"Status type not found: {type_id}") from exc

    def _get_type_by_name(self, workspace_id: str, type_name: str) -> StatusTypeRecord:
        row = (
            StatusTypeRecord
            .select()
            .where(
                (StatusTypeRecord.workspace == workspace_id)
                & (StatusTypeRecord.name == type_name)
            )
            .first()
        )
        if row is None:
            raise FileNotFoundError(f"Status type not found: {workspace_id}/{type_name}")
        return row

    def _get_template_row(self, template_id: int) -> StatusTableTemplateRecord:
        row = (
            StatusTableTemplateRecord
            .select(StatusTableTemplateRecord, StatusTypeRecord)
            .join(StatusTypeRecord)
            .where(StatusTableTemplateRecord.id == template_id)
            .first()
        )
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
            .select(StoryStatusTableRecord, StatusTableTemplateRecord, StatusTypeRecord)
            .join(StatusTableTemplateRecord)
            .join(StatusTypeRecord)
            .where(StoryStatusTableRecord.id == mount_id)
            .first()
        )
        if row is None:
            raise FileNotFoundError(f"Story status table mount not found: {mount_id}")
        return row

    def _get_session_row(self, session_id: str) -> SessionRecord:
        try:
            return SessionRecord.get_by_id(session_id)
        except DoesNotExist as exc:
            raise FileNotFoundError(f"Session not found: {session_id}") from exc

    def _get_session_type_by_name(self, session_id: str, type_name: str) -> SessionStatusTypeRecord:
        row = (
            SessionStatusTypeRecord
            .select()
            .where(
                (SessionStatusTypeRecord.session == session_id)
                & (SessionStatusTypeRecord.name == type_name)
            )
            .first()
        )
        if row is None:
            raise FileNotFoundError(f"Session status type not found: {session_id}/{type_name}")
        return row

    def _get_session_table_row(self, table_id: int) -> SessionStatusTableRecord:
        row = (
            SessionStatusTableRecord
            .select(SessionStatusTableRecord, SessionStatusTypeRecord)
            .join(SessionStatusTypeRecord)
            .where(SessionStatusTableRecord.id == table_id)
            .first()
        )
        if row is None:
            raise FileNotFoundError(f"Session status table not found: {table_id}")
        return row

    def _find_session_table(
        self,
        session_id: str,
        type_name: str,
        table_name: str,
    ) -> SessionStatusTableRecord | None:
        return (
            SessionStatusTableRecord
            .select(SessionStatusTableRecord, SessionStatusTypeRecord)
            .join(SessionStatusTypeRecord)
            .where(
                (SessionStatusTableRecord.session == session_id)
                & (SessionStatusTypeRecord.name == type_name)
                & (SessionStatusTableRecord.name == table_name)
            )
            .first()
        )


def _to_status_type(row: StatusTypeRecord) -> models.StatusType:
    return models.StatusType(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        name=str(row.name),
        builtin_key=str(row.builtin_key or ""),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_template(
    row: StatusTableTemplateRecord,
    workspace_root: Path,
) -> models.StatusTableTemplate:
    document = _read_status_document(resolve_workspace_relative_path(workspace_root, row.relative_path))
    headers, rows = _status_data_from_document(document)
    status_type = row.status_type
    return models.StatusTableTemplate(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        type_id=int(row.type_id),
        type_name=str(document.get("typeName") or status_type.name),
        builtin_key=str(document.get("builtinKey") or status_type.builtin_key or ""),
        name=str(document.get("name") or row.name),
        relative_path=str(row.relative_path),
        description=str(document.get("description") or row.description or ""),
        headers=headers,
        rows=rows,
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_story_mount(row: StoryStatusTableRecord) -> models.StoryStatusTable:
    template = row.status_table
    status_type = template.status_type
    return models.StoryStatusTable(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        status_table_id=int(row.status_table_id),
        type_id=int(template.type_id),
        type_name=str(status_type.name),
        builtin_key=str(status_type.builtin_key or ""),
        table_name=str(template.name),
        relative_path=str(template.relative_path),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_session_type(row: SessionStatusTypeRecord) -> models.SessionStatusType:
    source_type_id = None if row.source_type_id is None else int(row.source_type_id)
    return models.SessionStatusType(
        id=int(row.id),
        session_id=str(row.session_id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        source_type_id=source_type_id,
        name=str(row.name),
        builtin_key=str(row.builtin_key or ""),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_session_table(
    row: SessionStatusTableRecord,
    workspace_root: Path,
) -> models.SessionStatusTable:
    document = _read_status_document(resolve_workspace_relative_path(workspace_root, row.relative_path))
    headers, rows = _status_data_from_document(document)
    session_type = row.session_type
    source_table_id = None if row.source_table_id is None else int(row.source_table_id)
    return models.SessionStatusTable(
        id=int(row.id),
        session_id=str(row.session_id),
        session_type_id=int(row.session_type_id),
        workspace_id=str(session_type.workspace_id),
        story_id=int(session_type.story_id),
        source_table_id=source_table_id,
        type_name=str(document.get("typeName") or session_type.name),
        builtin_key=str(document.get("builtinKey") or session_type.builtin_key or ""),
        name=str(document.get("name") or row.name),
        relative_path=str(row.relative_path),
        description=str(document.get("description") or row.description or ""),
        headers=headers,
        rows=rows,
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _validate_name(name: str, label: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label} name must not be empty")
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"{label} name must not contain path separators: {name!r}")


def _template_relative_path(type_name: str, table_name: str) -> str:
    return f"{_TEMPLATE_STATUS_DIR}/{type_name}/{table_name}{_STATUS_FILE_SUFFIX}"


def _template_type_relative_path(type_name: str) -> str:
    return f"{_TEMPLATE_STATUS_DIR}/{type_name}"


def _session_root_relative_path(story_id: int, session_id: str) -> str:
    return f"{_SESSION_STORIES_DIR}/{story_id}/{session_id}"


def _session_status_root_relative_path(story_id: int, session_id: str) -> str:
    return f"{_session_root_relative_path(story_id, session_id)}/{_SESSION_STATUS_DIR}"


def _session_relative_path(
    story_id: int,
    session_id: str,
    type_name: str,
    table_name: str,
) -> str:
    return f"{_SESSION_STORIES_DIR}/{story_id}/{session_id}/{_SESSION_STATUS_DIR}/{type_name}/{table_name}{_STATUS_FILE_SUFFIX}"


def _read_status_json(path: Path) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    return _status_data_from_document(_read_status_document(path))


def _status_data_from_document(document: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    key_column = str(document.get("keyColumn") or models.STATUS_KEY_COLUMN)
    value_column = str(document.get("valueColumn") or models.STATUS_VALUE_COLUMN)
    rows: list[tuple[str, str]] = []
    for raw_row in _iter_status_rows(document):
        rows.append((str(raw_row.get("key", "")), str(raw_row.get("value", ""))))
    return (key_column, value_column), tuple(rows)


def _read_status_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Status table JSON must be an object: {path}")
    if data.get("kind") != _STATUS_TABLE_KIND or data.get("mode") != _STATUS_TABLE_MODE:
        raise ValueError(f"Unsupported status table JSON: {path}")
    return data


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


def _write_status_json(
    path: Path,
    *,
    type_name: str,
    name: str,
    builtin_key: str,
    description: str,
    headers: Iterable[str],
    rows: Iterable[Iterable[str]],
    metadata_json: str,
) -> None:
    existing_locks = _locked_keys_from_existing_document(path)
    document = _build_status_document(
        type_name=type_name,
        name=name,
        builtin_key=builtin_key,
        description=description,
        headers=headers,
        rows=rows,
        metadata_json=metadata_json,
        existing_locks=existing_locks,
    )
    _write_status_document(path, document)


def _write_status_document(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _build_status_document(
    *,
    type_name: str,
    name: str,
    builtin_key: str,
    description: str,
    headers: Iterable[str],
    rows: Iterable[Iterable[str]],
    metadata_json: str,
    existing_locks: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    output_headers, output_rows = _materialize_table_data(headers, rows)
    key_column = output_headers[0] if output_headers else models.STATUS_KEY_COLUMN
    value_column = output_headers[1] if len(output_headers) > 1 else models.STATUS_VALUE_COLUMN
    locked_by_key = dict(existing_locks or {})
    metadata = _parse_metadata(metadata_json)

    json_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in output_rows:
        key = row[0] if row else ""
        if not key:
            raise ValueError("Status table row key must not be empty")
        if key in seen:
            raise ValueError(f"Status table key is duplicated: {key}")
        seen.add(key)
        value = row[1] if len(row) > 1 else ""
        locked = locked_by_key.get(key)
        if locked is None:
            locked = builtin_key == SCENE_BUILTIN_KEY and key in SCENE_DEFAULT_LOCKED_KEYS
        json_rows.append({
            "key": key,
            "value": value,
            "runtimeKeyLocked": bool(locked),
            "metadata": {},
        })

    return {
        "schemaVersion": 1,
        "kind": _STATUS_TABLE_KIND,
        "mode": _STATUS_TABLE_MODE,
        "typeName": str(type_name),
        "name": str(name),
        "builtinKey": str(builtin_key or ""),
        "description": str(description or ""),
        "keyColumn": str(key_column),
        "valueColumn": str(value_column),
        "rows": json_rows,
        "metadata": metadata,
    }


def _iter_status_rows(document: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    raw_rows = document.get("rows", [])
    if not isinstance(raw_rows, list):
        return ()
    rows: list[dict[str, Any]] = []
    for item in raw_rows:
        if isinstance(item, dict):
            rows.append(item)
    return tuple(rows)


def _locked_keys_from_existing_document(path: Path) -> dict[str, bool]:
    try:
        document = _read_status_document(path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return {}
    return {
        str(row.get("key", "")): bool(row.get("runtimeKeyLocked", False))
        for row in _iter_status_rows(document)
        if row.get("key")
    }


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _unlink_missing_ok(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _remove_empty_parents(start: Path, stop: Path) -> None:
    stop = stop.resolve()
    current = start.resolve()
    while True:
        if current == stop or not current.exists():
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _touch(model: type, row_id: int) -> None:
    (
        model.update(updated_at=SQL("CURRENT_TIMESTAMP"))
        .where(model._meta.primary_key == row_id)
        .execute()
    )


def _rows_to_attrs(rows: Iterable[Iterable[str]]) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for row in rows:
        cells = list(row)
        if len(cells) >= 2:
            attrs[str(cells[0])] = str(cells[1])
    return attrs
