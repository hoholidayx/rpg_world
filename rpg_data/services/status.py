"""Status table service backed by SQLite document records."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Callable, Iterable, Mapping

from peewee import Database, DoesNotExist, IntegrityError, SQL

from rpg_data import models
from rpg_data.repositories.records import (
    CharacterRecord,
    SessionRecord,
    SessionStatusDeferredProgressRecord,
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
        mounts = self._list_story_status_mounts(workspace_id, story_id)
        with self._database.atomic():
            self._create_session_template_copies(
                session_id,
                workspace_id,
                story_id,
                mounts,
            )
        tables = self.list_tables(session_id)
        logger.info("initialized session status tables session_id=%s table_count=%s", session_id, len(tables))
        return tables

    def reset_session_tables(self, session_id: str) -> models.SessionStatusResetResult:
        """Rebuild Story copies while preserving native table structure and IDs."""

        with self._database.atomic():
            session = self._get_session_row(session_id)
            workspace_id = str(session.workspace_id)
            story_id = int(session.story_id)
            existing_tables = self.list_tables(session_id)
            template_tables = [
                table
                for table in existing_tables
                if table.origin == models.STATUS_ORIGIN_TEMPLATE_COPY
            ]
            native_tables = [
                table
                for table in existing_tables
                if table.origin == models.STATUS_ORIGIN_SESSION_NATIVE
            ]
            mounts = self._list_story_status_mounts(workspace_id, story_id)
            mounted_names = {str(mount.status_table.name) for mount in mounts}
            conflicts = sorted(
                table.name for table in native_tables if table.name in mounted_names
            )
            if conflicts:
                joined = ", ".join(conflicts)
                raise ValueError(
                    "Session-native status table names conflict with current Story templates: "
                    + joined
                )

            table_ids = [table.id for table in existing_tables]
            deferred_progress_cleared = 0
            if table_ids:
                deferred_progress_cleared = int(
                    SessionStatusDeferredProgressRecord
                    .delete()
                    .where(
                        SessionStatusDeferredProgressRecord.session_status_table.in_(
                            table_ids
                        )
                    )
                    .execute()
                )

            if template_tables:
                (
                    SessionStatusTableRecord
                    .delete()
                    .where(
                        SessionStatusTableRecord.id.in_(
                            [table.id for table in template_tables]
                        )
                    )
                    .execute()
                )

            for table in native_tables:
                cleared_document = _document_for_kind(
                    table.status_kind,
                    table.document.with_cleared_values(),
                )
                updated = (
                    SessionStatusTableRecord
                    .update(
                        document_json=models.serialize_status_document(cleared_document),
                        updated_at=SQL("CURRENT_TIMESTAMP"),
                    )
                    .where(SessionStatusTableRecord.id == table.id)
                    .execute()
                )
                if updated != 1:
                    raise RuntimeError(
                        f"Session-native status table disappeared during reset: {table.id}"
                    )

            initialized_count = self._create_session_template_copies(
                session_id,
                workspace_id,
                story_id,
                mounts,
            )

        logger.info(
            "reset session status tables session_id=%s template_cleared=%s template_initialized=%s native_reset=%s deferred_progress_cleared=%s",
            session_id,
            len(template_tables),
            initialized_count,
            len(native_tables),
            deferred_progress_cleared,
        )
        return models.SessionStatusResetResult(
            session_id=session_id,
            template_tables_cleared=len(template_tables),
            template_tables_initialized=initialized_count,
            native_tables_reset=len(native_tables),
            deferred_progress_cleared=deferred_progress_cleared,
        )

    @staticmethod
    def _list_story_status_mounts(
        workspace_id: str,
        story_id: int,
    ) -> list[StoryStatusTableRecord]:
        return list(
            StoryStatusTableRecord
            .select(StoryStatusTableRecord, StatusTableTemplateRecord)
            .join(StatusTableTemplateRecord)
            .where(
                (StoryStatusTableRecord.workspace == workspace_id)
                & (StoryStatusTableRecord.story == story_id)
            )
            .order_by(StoryStatusTableRecord.sort_order, StoryStatusTableRecord.id)
        )

    @staticmethod
    def _create_session_template_copies(
        session_id: str,
        workspace_id: str,
        story_id: int,
        mounts: list[StoryStatusTableRecord],
    ) -> int:
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
                metadata_json=_session_metadata_for_mount(
                    str(template.metadata_json or "{}"),
                    mount,
                ),
            )
        return len(mounts)

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
        result: list[models.SessionStatusTable] = []
        for table in self.list_tables(session_id, include_scene=False):
            prepared = self._prepare_context_table_character_name(table)
            if prepared is not None:
                result.append(prepared)
        return result

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

    def get_table_for_session(
        self,
        session_id: str,
        table_id: int,
    ) -> models.SessionStatusTable:
        row = self._get_session_table_row(table_id)
        if str(row.session_id) != str(session_id):
            logger.warning(
                "rejected cross-session status table access session_id=%s table_id=%s actual_session_id=%s",
                session_id,
                table_id,
                row.session_id,
            )
            raise FileNotFoundError(
                f"Session status table is unavailable: {session_id}/{table_id}"
            )
        return _to_session_table(row)

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

    def save_table_for_session(
        self,
        session_id: str,
        table_id: int,
        document: models.StatusTableDocument,
        *,
        expected_status_kind: str,
        base_document: models.StatusTableDocument | None = None,
        write_source: str = "runtime",
    ) -> models.SessionStatusTable:
        """Save a runtime document after repeating session and kind checks."""
        row = self._get_session_table_row(table_id)
        if str(row.session_id) != str(session_id):
            logger.warning(
                "rejected cross-session status table write session_id=%s table_id=%s actual_session_id=%s source=%s",
                session_id,
                table_id,
                row.session_id,
                write_source,
            )
            raise FileNotFoundError(
                f"Session status table is unavailable: {session_id}/{table_id}"
            )

        expected_kind = models.validate_status_kind(expected_status_kind)
        actual_kind = models.validate_status_kind(str(row.status_kind))
        if actual_kind != expected_kind:
            logger.warning(
                "rejected status table kind mismatch session_id=%s table_id=%s expected_kind=%s actual_kind=%s source=%s",
                session_id,
                table_id,
                expected_kind,
                actual_kind,
                write_source,
            )
            raise ValueError(
                f"Status table kind changed before write: expected {expected_kind}, got {actual_kind}"
            )

        current_document = _parse_row_document(row)
        if base_document is not None and current_document != base_document:
            logger.warning(
                "overwriting concurrently changed status table with last-write-wins session_id=%s table_id=%s table_name=%s source=%s",
                session_id,
                table_id,
                row.name,
                write_source,
            )

        row.document_json = models.serialize_status_document(
            _document_for_kind(actual_kind, document)
        )
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        row.save()
        return _to_session_table(row)

    def list_deferred_progress(
        self,
        session_id: str,
    ) -> list[models.StatusDeferredProgress]:
        query = (
            SessionStatusDeferredProgressRecord
            .select(
                SessionStatusDeferredProgressRecord,
                SessionStatusTableRecord,
            )
            .join(SessionStatusTableRecord)
            .where(SessionStatusTableRecord.session == session_id)
        )
        return [
            models.StatusDeferredProgress(
                session_status_table_id=int(row.session_status_table_id),
                field_key=str(row.field_key),
                last_processed_turn_id=max(0, int(row.last_processed_turn_id)),
            )
            for row in query
        ]

    def clamp_deferred_progress(
        self,
        session_id: str,
        max_turn_id: int,
    ) -> int:
        """Clamp progress after history truncation without rolling back values."""
        boundary = max(0, int(max_turn_id))
        table_ids = (
            SessionStatusTableRecord
            .select(SessionStatusTableRecord.id)
            .where(SessionStatusTableRecord.session == session_id)
        )
        return (
            SessionStatusDeferredProgressRecord
            .update(
                last_processed_turn_id=boundary,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionStatusDeferredProgressRecord.session_status_table.in_(table_ids))
                & (SessionStatusDeferredProgressRecord.last_processed_turn_id > boundary)
            )
            .execute()
        )

    def commit_deferred_update(
        self,
        session_id: str,
        table_id: int,
        document: models.StatusTableDocument,
        *,
        processed_keys: Iterable[str],
        last_processed_turn_id: int,
        base_document: models.StatusTableDocument | None = None,
    ) -> models.SessionStatusTable:
        """Atomically write deferred values and advance per-field progress."""
        if last_processed_turn_id <= 0:
            raise ValueError("last_processed_turn_id must be positive")
        keys = tuple(dict.fromkeys(str(key) for key in processed_keys if str(key)))
        if not keys:
            raise ValueError("processed_keys must not be empty")
        row = self._get_session_table_row(table_id)
        if str(row.session_id) != str(session_id):
            raise FileNotFoundError(
                f"Session status table is unavailable: {session_id}/{table_id}"
            )
        if str(row.status_kind) != models.STATUS_KIND_NORMAL:
            raise PermissionError("Deferred updates only support normal status tables")
        validated = document.validated()
        for key in keys:
            field = validated.row_for_key(key)
            if field is None:
                raise KeyError(f"Status table key not found: {key}")
            if field.update_frequency != models.STATUS_UPDATE_FREQUENCY_DEFERRED:
                raise PermissionError(f"Status field is not deferred: {key}")

        current_document = _parse_row_document(row)
        if base_document is not None and current_document != base_document:
            logger.warning(
                "overwriting concurrently changed deferred status table with last-write-wins session_id=%s table_id=%s",
                session_id,
                table_id,
            )
        with self._database.atomic():
            row.document_json = models.serialize_status_document(validated)
            row.updated_at = SQL("CURRENT_TIMESTAMP")
            row.save()
            for key in keys:
                (
                    SessionStatusDeferredProgressRecord
                    .insert(
                        session_status_table=table_id,
                        field_key=key,
                        last_processed_turn_id=last_processed_turn_id,
                        updated_at=SQL("CURRENT_TIMESTAMP"),
                    )
                    .on_conflict(
                        conflict_target=(
                            SessionStatusDeferredProgressRecord.session_status_table,
                            SessionStatusDeferredProgressRecord.field_key,
                        ),
                        update={
                            SessionStatusDeferredProgressRecord.last_processed_turn_id:
                                last_processed_turn_id,
                            SessionStatusDeferredProgressRecord.updated_at:
                                SQL("CURRENT_TIMESTAMP"),
                        },
                    )
                    .execute()
                )
        return _to_session_table(row)

    def commit_bootstrap_state(
        self,
        session_id: str,
        documents: Iterable[models.StatusBootstrapDocument],
        *,
        deferred_progress: Mapping[int, Iterable[str]],
        boundary_turn_id: int,
    ) -> list[models.SessionStatusTable]:
        """Atomically publish derivation-bootstrap documents and progress.

        All LLM work happens against an in-memory scratch.  This method is the
        only durable boundary, so a validation or SQL failure cannot expose a
        partially bootstrapped session.
        """
        if boundary_turn_id <= 0:
            raise ValueError("boundary_turn_id must be positive")

        staged = tuple(documents)
        if len({item.table_id for item in staged}) != len(staged):
            raise ValueError("bootstrap documents contain duplicate table IDs")
        progress_by_table = {
            int(table_id): tuple(dict.fromkeys(
                str(key) for key in keys if str(key)
            ))
            for table_id, keys in deferred_progress.items()
        }
        affected_ids = {item.table_id for item in staged} | set(progress_by_table)
        rows: dict[int, SessionStatusTableRecord] = {}
        current_documents: dict[int, models.StatusTableDocument] = {}

        for table_id in affected_ids:
            row = self._get_session_table_row(table_id)
            if str(row.session_id) != str(session_id):
                raise FileNotFoundError(
                    f"Session status table is unavailable: {session_id}/{table_id}"
                )
            rows[table_id] = row
            current_documents[table_id] = _parse_row_document(row)

        for item in staged:
            row = rows[item.table_id]
            actual_kind = models.validate_status_kind(str(row.status_kind))
            expected_kind = models.validate_status_kind(item.status_kind)
            if actual_kind != expected_kind:
                raise ValueError(
                    "Status table kind changed before bootstrap write: "
                    f"expected {expected_kind}, got {actual_kind}"
                )
            item.document.validated()
            if current_documents[item.table_id] != item.base_document:
                logger.warning(
                    "overwriting concurrently changed status table with last-write-wins "
                    "session_id=%s table_id=%s source=derivation_bootstrap",
                    session_id,
                    item.table_id,
                )

        for table_id, keys in progress_by_table.items():
            row = rows[table_id]
            if str(row.status_kind) != models.STATUS_KIND_NORMAL:
                raise PermissionError(
                    "Deferred bootstrap progress only supports normal status tables"
                )
            document = next(
                (
                    item.document
                    for item in staged
                    if item.table_id == table_id
                ),
                current_documents[table_id],
            ).validated()
            for key in keys:
                field = document.row_for_key(key)
                if field is None:
                    raise KeyError(f"Status table key not found: {key}")
                if field.update_frequency != models.STATUS_UPDATE_FREQUENCY_DEFERRED:
                    raise PermissionError(f"Status field is not deferred: {key}")

        with self._database.atomic():
            for item in staged:
                row = rows[item.table_id]
                row.document_json = models.serialize_status_document(
                    _document_for_kind(str(row.status_kind), item.document)
                )
                row.updated_at = SQL("CURRENT_TIMESTAMP")
                row.save()
            for table_id, keys in progress_by_table.items():
                for key in keys:
                    (
                        SessionStatusDeferredProgressRecord
                        .insert(
                            session_status_table=table_id,
                            field_key=key,
                            last_processed_turn_id=boundary_turn_id,
                            updated_at=SQL("CURRENT_TIMESTAMP"),
                        )
                        .on_conflict(
                            conflict_target=(
                                SessionStatusDeferredProgressRecord.session_status_table,
                                SessionStatusDeferredProgressRecord.field_key,
                            ),
                            update={
                                SessionStatusDeferredProgressRecord.last_processed_turn_id:
                                    boundary_turn_id,
                                SessionStatusDeferredProgressRecord.updated_at:
                                    SQL("CURRENT_TIMESTAMP"),
                            },
                        )
                        .execute()
                    )
        return [_to_session_table(rows[item.table_id]) for item in staged]

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
        _required_story_character_identity(row)
        return row

    def _prepare_context_table_character_name(
        self,
        table: models.SessionStatusTable,
    ) -> models.SessionStatusTable | None:
        if table.origin != models.STATUS_ORIGIN_TEMPLATE_COPY:
            return table
        metadata = _parse_metadata_json(table.metadata_json)
        mount = metadata.get("storyStatusMount")
        if not isinstance(mount, dict):
            return table

        character_mount_id = _optional_positive_int(mount.get("characterMountId"))
        expected_character_id = _optional_positive_int(mount.get("characterId"))
        has_character_binding = (
            mount.get("characterMountId") is not None
            or mount.get("characterId") is not None
            or bool(str(mount.get("characterName") or "").strip())
        )
        if not has_character_binding:
            return table

        character_name = str(mount.get("characterName") or "").strip()
        if character_name:
            return table

        character_mount = self._find_context_character_mount(
            table,
            character_mount_id=character_mount_id,
        )
        if character_mount is None and expected_character_id is not None:
            status_mount_id = _optional_positive_int(mount.get("mountId"))
            status_mount = None
            if status_mount_id is not None:
                status_mount = (
                    StoryStatusTableRecord
                    .select()
                    .where(
                        (StoryStatusTableRecord.id == status_mount_id)
                        & (StoryStatusTableRecord.workspace == table.workspace_id)
                        & (StoryStatusTableRecord.story == table.story_id)
                    )
                    .first()
                )
            fallback_character_mount_id = (
                _story_character_mount_id(status_mount)
                if status_mount is not None
                else None
            )
            if fallback_character_mount_id is not None:
                character_mount_id = fallback_character_mount_id
                character_mount = self._find_context_character_mount(
                    table,
                    character_mount_id=character_mount_id,
                )

        if character_mount is not None:
            character_id = None
            try:
                character_id, character_name = _required_story_character_identity(character_mount)
            except ValueError:
                character_name = ""
            if (
                expected_character_id is not None
                and character_id != expected_character_id
            ):
                character_name = ""
            if character_name and character_id is not None:
                mount["characterMountId"] = character_mount_id
                mount["characterId"] = character_id
                mount["characterName"] = character_name
                repaired_metadata_json = json.dumps(metadata, ensure_ascii=False)
                SessionStatusTableRecord.update(
                    metadata_json=repaired_metadata_json,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                ).where(
                    (SessionStatusTableRecord.id == table.id)
                    & (SessionStatusTableRecord.session == table.session_id)
                ).execute()
                logger.warning(
                    "backfilled missing status table character name session_id=%s table_id=%s character_mount_id=%s character_name=%s",
                    table.session_id,
                    table.id,
                    character_mount_id,
                    character_name,
                )
                return replace(table, metadata_json=repaired_metadata_json)

        logger.warning(
            "excluded character-bound status table from context because character name is unresolved session_id=%s table_id=%s character_mount_id=%s character_id=%s",
            table.session_id,
            table.id,
            mount.get("characterMountId"),
            mount.get("characterId"),
        )
        return None

    @staticmethod
    def _find_context_character_mount(
        table: models.SessionStatusTable,
        *,
        character_mount_id: int | None,
    ) -> StoryCharacterRecord | None:
        if character_mount_id is None:
            return None
        return (
            StoryCharacterRecord
            .select(StoryCharacterRecord, CharacterRecord)
            .join(CharacterRecord)
            .where(
                (StoryCharacterRecord.id == character_mount_id)
                & (StoryCharacterRecord.workspace == table.workspace_id)
                & (StoryCharacterRecord.story == table.story_id)
            )
            .first()
        )

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
    character_name = None
    if character_mount_id is not None:
        try:
            character_id, character_name = _required_story_character_identity(mount.story_character)
        except DoesNotExist as exc:
            raise ValueError(
                f"Story character mount cannot resolve a named character: {character_mount_id}"
            ) from exc
    metadata["storyStatusMount"] = {
        "mountId": int(mount.id),
        "mountOrigin": models.validate_story_status_mount_origin(str(mount.mount_origin)),
        "characterMountId": character_mount_id,
        "characterId": character_id,
        "characterName": character_name,
    }
    return json.dumps(metadata, ensure_ascii=False)


def _story_character_mount_id(row: StoryStatusTableRecord) -> int | None:
    raw_value = row.__data__.get("story_character")
    return None if raw_value is None else int(raw_value)


def _required_story_character_identity(row: StoryCharacterRecord) -> tuple[int, str]:
    try:
        character = row.character
    except DoesNotExist as exc:
        raise ValueError(
            f"Story character mount cannot resolve character: {int(row.id)}"
        ) from exc
    character_name = str(character.name or "").strip()
    if not character_name:
        raise ValueError(
            f"Story character mount requires a non-empty character name: {int(row.id)}"
        )
    return int(character.id), character_name


def _optional_positive_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


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
            row.update_frequency,
            row.update_rule,
            row.deferred_interval_turns,
        )
        for row in document.rows
    )
    for row in rows:
        if row.update_frequency != models.STATUS_UPDATE_FREQUENCY_REALTIME:
            raise ValueError("scene status fields must use realtime updateFrequency")
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
