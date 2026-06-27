"""Status table service backed by SQL indexes and CSV content files."""

from __future__ import annotations

import csv
import logging
import shutil
from pathlib import Path
from typing import Iterable, Mapping

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
SCENE_DEFAULT_HEADERS = ("属性", "值")
SCENE_PROTECTED_ATTRS = {"时间", "位置", "在场人物"}
_TEMPLATE_STATUS_DIR = "template_status"
_SESSION_STORIES_DIR = "stories"
_SESSION_STATUS_DIR = "status"


class StatusTableService:
    """Manage status table indexes in SQL and table content in CSV files."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

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
        return [_to_status_type(row) for row in rows]

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
            raise ValueError(f"Status type already exists: {name}") from exc
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
        try:
            for old_path, new_path, _template in moves:
                if old_path == new_path:
                    continue
                if not old_path.is_file():
                    raise FileNotFoundError(str(old_path))
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                moved.append((old_path, new_path))
            with self._database.atomic():
                row.name = new_name
                row.updated_at = SQL("CURRENT_TIMESTAMP")
                row.save()
                for _old_path, _new_path, template in moves:
                    template.relative_path = _template_relative_path(new_name, str(template.name))
                    template.updated_at = SQL("CURRENT_TIMESTAMP")
                    template.save()
        except Exception:
            for old_path, new_path in reversed(moved):
                if new_path.exists() and not old_path.exists():
                    old_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(new_path), str(old_path))
            raise

        _remove_empty_parents(
            resolve_workspace_relative_path(workspace_root, _template_type_relative_path(old_name)),
            resolve_workspace_relative_path(workspace_root, _TEMPLATE_STATUS_DIR),
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
        return [_to_template(row, workspace_root) for row in query]

    def get_template(self, template_id: int) -> models.StatusTableTemplate | None:
        row = (
            StatusTableTemplateRecord
            .select(StatusTableTemplateRecord, StatusTypeRecord)
            .join(StatusTypeRecord)
            .where(StatusTableTemplateRecord.id == template_id)
            .first()
        )
        if row is None:
            return None
        return _to_template(row, self._workspace_root(str(row.workspace_id)))

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

        _write_csv(path, headers, rows)
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

        old_path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        new_relative_path = _template_relative_path(str(target_type.name), target_name)
        new_path = resolve_workspace_relative_path(workspace_root, new_relative_path)
        current_headers, current_rows = _read_csv(old_path)
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
            _write_csv(new_path, output_headers, output_rows)
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
        return _to_template(self._get_template_row(template_id), workspace_root)

    def delete_template(self, template_id: int) -> None:
        row = self._get_template_row(template_id)
        workspace_root = self._workspace_root(str(row.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, row.relative_path)
        with self._database.atomic():
            row.delete_instance(recursive=True)
        _unlink_missing_ok(path)
        _remove_empty_parents(path.parent, resolve_workspace_relative_path(workspace_root, _TEMPLATE_STATUS_DIR))

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
        return [_to_story_mount(row) for row in query]

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
            raise ValueError(f"Status table already mounted to story: {story_id}/{template_id}") from exc
        return _to_story_mount(self._get_story_mount_row(int(row.id)))

    def unmount_template(self, mount_id: int) -> None:
        row = self._get_story_mount_row(mount_id)
        row.delete_instance()

    # ------------------------------------------------------------------
    # Session copies
    # ------------------------------------------------------------------

    def initialize_session_tables(self, session_id: str) -> list[models.SessionStatusTable]:
        session = self._get_session_row(session_id)
        if SessionStatusTableRecord.select().where(SessionStatusTableRecord.session == session_id).exists():
            return self.list_tables(session_id)

        workspace_id = str(session.workspace_id)
        story_id = int(session.story_id)
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
        try:
            with self._database.atomic():
                for mount in mounts:
                    template = mount.status_table
                    type_row = template.status_type
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

                    source_path = resolve_workspace_relative_path(workspace_root, template.relative_path)
                    if not source_path.is_file():
                        raise FileNotFoundError(str(source_path))
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
            for path in reversed(created_files):
                _unlink_missing_ok(path)
                _remove_empty_parents(
                    path.parent,
                    resolve_workspace_relative_path(workspace_root, _session_root_relative_path(story_id, session_id)),
                )
            raise
        return self.list_tables(session_id)

    def list_session_types(self, session_id: str) -> list[models.SessionStatusType]:
        rows = (
            SessionStatusTypeRecord
            .select()
            .where(SessionStatusTypeRecord.session == session_id)
            .order_by(SessionStatusTypeRecord.sort_order, SessionStatusTypeRecord.id)
        )
        return [_to_session_type(row) for row in rows]

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
            raise ValueError(f"Session status type already exists: {name}") from exc
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
        return [
            _to_session_table(row, self._workspace_root(str(row.session_type.workspace_id)))
            for row in query
        ]

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
            except FileNotFoundError as exc:
                logger.debug("skip missing status table CSV for context: %s", exc)
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
        return _to_session_table(row, self._workspace_root(str(row.session_type.workspace_id)))

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

        _write_csv(path, headers, rows)
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
        _write_csv(path, headers, rows)
        _touch(SessionStatusTableRecord, int(row.id))
        return self.get_table(session_id, type_name, table_name)

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

    def clear_unindexed_session_files(self, session_id: str) -> list[str]:
        """Delete session status CSV files that are not referenced by SQL indexes.

        SQL remains the complete index for status tables. This cleanup only scans
        the current session's status copy directory and removes orphan ``.csv``
        files under it; indexed files and non-CSV files are left untouched.
        Returned paths are relative to the workspace root.
        """

        session = self._get_session_row(session_id)
        workspace_root = self._workspace_root(str(session.workspace_id))
        status_root = resolve_workspace_relative_path(
            workspace_root,
            _session_status_root_relative_path(int(session.story_id), session_id),
        )
        if not status_root.is_dir():
            return []

        indexed_paths = {
            resolve_workspace_relative_path(workspace_root, row.relative_path).resolve()
            for row in SessionStatusTableRecord
            .select(SessionStatusTableRecord.relative_path)
            .where(SessionStatusTableRecord.session == session_id)
        }
        removed: list[str] = []
        workspace_root_resolved = workspace_root.resolve()
        for path in sorted(status_root.rglob("*.csv")):
            resolved = path.resolve()
            if resolved in indexed_paths:
                continue
            _unlink_missing_ok(path)
            removed.append(resolved.relative_to(workspace_root_resolved).as_posix())
            _remove_empty_parents(path.parent, status_root)
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
            return None
        return _to_session_table(row, self._workspace_root(str(row.session_type.workspace_id)))

    def get_scene_attrs(self, session_id: str) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            return None
        return _rows_to_attrs(table.rows)

    def replace_scene_attrs(
        self,
        session_id: str,
        attrs: Mapping[str, str],
    ) -> dict[str, str] | None:
        table = self.get_active_scene_table(session_id)
        if table is None:
            return None
        clean_attrs = {str(key): str(value) for key, value in attrs.items()}
        self.save_table(
            session_id,
            table.type_name,
            table.name,
            SCENE_DEFAULT_HEADERS,
            [[key, value] for key, value in clean_attrs.items()],
        )
        return clean_attrs

    def set_scene_attr(self, session_id: str, key: str, value: str) -> dict[str, str] | None:
        attrs = self.get_scene_attrs(session_id)
        if attrs is None:
            return None
        attrs[str(key)] = str(value)
        return self.replace_scene_attrs(session_id, attrs)

    def delete_scene_attr(self, session_id: str, key: str) -> dict[str, str] | None:
        attrs = self.get_scene_attrs(session_id)
        if attrs is None:
            return None
        if key not in SCENE_PROTECTED_ATTRS:
            attrs.pop(key, None)
        return self.replace_scene_attrs(session_id, attrs)

    # ------------------------------------------------------------------
    # Internal lookups
    # ------------------------------------------------------------------

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
    headers, rows = _read_csv(resolve_workspace_relative_path(workspace_root, row.relative_path))
    status_type = row.status_type
    return models.StatusTableTemplate(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        type_id=int(row.type_id),
        type_name=str(status_type.name),
        builtin_key=str(status_type.builtin_key or ""),
        name=str(row.name),
        relative_path=str(row.relative_path),
        description=str(row.description or ""),
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
    headers, rows = _read_csv(resolve_workspace_relative_path(workspace_root, row.relative_path))
    session_type = row.session_type
    source_table_id = None if row.source_table_id is None else int(row.source_table_id)
    return models.SessionStatusTable(
        id=int(row.id),
        session_id=str(row.session_id),
        session_type_id=int(row.session_type_id),
        workspace_id=str(session_type.workspace_id),
        story_id=int(session_type.story_id),
        source_table_id=source_table_id,
        type_name=str(session_type.name),
        builtin_key=str(session_type.builtin_key or ""),
        name=str(row.name),
        relative_path=str(row.relative_path),
        description=str(row.description or ""),
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
    return f"{_TEMPLATE_STATUS_DIR}/{type_name}/{table_name}.csv"


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
    return f"{_SESSION_STORIES_DIR}/{story_id}/{session_id}/{_SESSION_STATUS_DIR}/{type_name}/{table_name}.csv"


def _read_csv(path: Path) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        raw_rows = list(csv.reader(fh))
    if not raw_rows:
        return (), ()
    headers = tuple(str(cell) for cell in raw_rows[0])
    rows = tuple(tuple(str(cell) for cell in row) for row in raw_rows[1:])
    return headers, rows


def _write_csv(path: Path, headers: Iterable[str], rows: Iterable[Iterable[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([str(item) for item in headers])
        for row in rows:
            writer.writerow([str(cell) for cell in row])


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
