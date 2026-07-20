"""Status table service backed by SQLite document records."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from typing import Iterator

from peewee import JOIN, Database, DoesNotExist, IntegrityError, SQL

from rpg_data.model import status as models
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

__all__ = ["StatusDataService"]

logger = logging.getLogger("rpg_data.status")


class StatusDataService:
    """Typed Status persistence, association reads, and atomic writes."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        logger.debug("status table service initialized database=%s", database)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._database.atomic():
            yield

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
        row.delete_instance()
        logger.info("deleted status template template_id=%s", template_id)

    def has_template_mounts(self, template_id: int) -> bool:
        self._get_template_row(template_id)
        return (
            StoryStatusTableRecord.select()
            .where(StoryStatusTableRecord.status_table == template_id)
            .exists()
        )

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

    def get_story_mount(self, mount_id: int) -> models.StoryStatusTable:
        return _to_story_mount(self._get_story_mount_row(mount_id))

    # ------------------------------------------------------------------
    # Session tables
    # ------------------------------------------------------------------

    def copy_story_mounts_to_session(
        self,
        session_id: str,
        mount_ids: Iterable[int],
    ) -> list[models.SessionStatusTable]:
        """Copy the exact Story mount set supplied by the caller."""

        session = self._get_session_row(session_id)
        workspace_id = str(session.workspace_id)
        story_id = int(session.story_id)
        mounts = self._require_story_mount_ids(
            workspace_id,
            story_id,
            mount_ids,
        )
        with self._database.atomic():
            self._create_session_template_copies(
                session_id,
                workspace_id,
                story_id,
                mounts,
            )
        return self.list_tables(session_id)

    def apply_session_reset_plan(
        self,
        session_id: str,
        plan: models.SessionStatusResetPlan,
    ) -> models.SessionStatusResetResult:
        """Apply one caller-prepared reset plan without choosing reset policy."""

        session = self._get_session_row(session_id)
        workspace_id = str(session.workspace_id)
        story_id = int(session.story_id)
        current = {table.id: table for table in self.list_tables(session_id)}
        delete_ids = _unique_positive_ids(plan.delete_table_ids, "delete_table_ids")
        progress_ids = _unique_positive_ids(
            plan.deferred_progress_table_ids,
            "deferred_progress_table_ids",
        )
        writes = tuple(plan.document_writes)
        write_ids = _unique_positive_ids(
            (write.table_id for write in writes),
            "document_writes",
        )
        referenced_ids = set(delete_ids) | set(progress_ids) | set(write_ids)
        missing_ids = referenced_ids.difference(current)
        if missing_ids:
            raise FileNotFoundError(
                "Session status tables not found: "
                + ", ".join(str(value) for value in sorted(missing_ids))
            )
        if set(delete_ids).intersection(write_ids):
            raise ValueError("status reset plan cannot delete and update the same table")
        mounts = self._require_story_mount_ids(
            workspace_id,
            story_id,
            plan.story_mount_ids,
        )

        with self._database.atomic():
            deferred_progress_cleared = 0
            if progress_ids:
                deferred_progress_cleared = int(
                    SessionStatusDeferredProgressRecord
                    .delete()
                    .where(
                        SessionStatusDeferredProgressRecord.session_status_table.in_(
                            progress_ids
                        )
                    )
                    .execute()
                )
            if delete_ids:
                deleted = int(
                    SessionStatusTableRecord
                    .delete()
                    .where(
                        (SessionStatusTableRecord.session == session_id)
                        & SessionStatusTableRecord.id.in_(delete_ids)
                    )
                    .execute()
                )
                if deleted != len(delete_ids):
                    raise RuntimeError("Session status tables changed during reset")
            for write in writes:
                document = write.document.validated()
                updated = (
                    SessionStatusTableRecord
                    .update(
                        document_json=models.serialize_status_document(document),
                        updated_at=SQL("CURRENT_TIMESTAMP"),
                    )
                    .where(
                        (SessionStatusTableRecord.session == session_id)
                        & (SessionStatusTableRecord.id == write.table_id)
                    )
                    .execute()
                )
                if updated != 1:
                    raise RuntimeError(
                        "Session status table changed during reset: "
                        f"{write.table_id}"
                    )
            initialized_count = self._create_session_template_copies(
                session_id,
                workspace_id,
                story_id,
                mounts,
            )
        return models.SessionStatusResetResult(
            session_id=session_id,
            template_tables_cleared=len(delete_ids),
            template_tables_initialized=initialized_count,
            native_tables_reset=len(writes),
            deferred_progress_cleared=deferred_progress_cleared,
        )

    @staticmethod
    def _require_story_mount_ids(
        workspace_id: str,
        story_id: int,
        mount_ids: Iterable[int],
    ) -> list[StoryStatusTableRecord]:
        normalized = _unique_positive_ids(mount_ids, "story_mount_ids")
        if not normalized:
            return []
        rows = list(
            StoryStatusTableRecord
            .select(StoryStatusTableRecord, StatusTableTemplateRecord)
            .join(StatusTableTemplateRecord)
            .where(
                (StoryStatusTableRecord.workspace == workspace_id)
                & (StoryStatusTableRecord.story == story_id)
                & (StoryStatusTableRecord.id.in_(normalized))
            )
            .order_by(StoryStatusTableRecord.sort_order, StoryStatusTableRecord.id)
        )
        found = {int(row.id) for row in rows}
        missing = set(normalized).difference(found)
        if missing:
            raise FileNotFoundError(
                "Story status mounts not found: "
                + ", ".join(str(value) for value in sorted(missing))
            )
        return rows

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
    ) -> list[models.SessionStatusTable]:
        query = SessionStatusTableRecord.select().where(SessionStatusTableRecord.session == session_id)
        if status_kind is not None:
            query = query.where(SessionStatusTableRecord.status_kind == models.validate_status_kind(status_kind))
        query = query.order_by(
            SessionStatusTableRecord.status_kind,
            SessionStatusTableRecord.sort_order,
            SessionStatusTableRecord.id,
        )
        result = [_to_session_table(row) for row in query]
        logger.debug("listed session status tables session_id=%s status_kind=%s count=%s", session_id, status_kind, len(result))
        return result

    def list_context_candidates(
        self,
        session_id: str,
    ) -> list[models.StatusContextCandidate]:
        """Return normal tables and association facts without visibility policy."""

        tables = self.list_tables(
            session_id,
            status_kind=models.STATUS_KIND_NORMAL,
        )
        source_ids = {
            table.source_table_id
            for table in tables
            if table.source_table_id is not None
        }
        mounts_by_source: dict[int, StoryStatusTableRecord] = {}
        if source_ids:
            story_id = tables[0].story_id
            for mount in (
                StoryStatusTableRecord.select()
                .where(
                    (StoryStatusTableRecord.story == story_id)
                    & StoryStatusTableRecord.status_table.in_(source_ids)
                )
            ):
                mounts_by_source[int(mount.status_table_id)] = mount

        metadata_by_table = {
            table.id: models.parse_session_status_metadata(table.metadata_json)
            for table in tables
        }
        character_mount_ids = {
            metadata.story_mount.character_mount_id
            for metadata in metadata_by_table.values()
            if metadata.story_mount is not None
            and metadata.story_mount.character_mount_id is not None
        }
        character_mount_ids.update(
            character_mount_id
            for mount in mounts_by_source.values()
            if (character_mount_id := _story_character_mount_id(mount)) is not None
        )
        characters_by_mount: dict[int, models.StatusCharacterIdentity] = {}
        if character_mount_ids:
            workspace_id = tables[0].workspace_id
            story_id = tables[0].story_id
            query = (
                StoryCharacterRecord.select(StoryCharacterRecord, CharacterRecord)
                .join(CharacterRecord, JOIN.LEFT_OUTER)
                .where(
                    (StoryCharacterRecord.id.in_(character_mount_ids))
                    & (StoryCharacterRecord.workspace == workspace_id)
                    & (StoryCharacterRecord.story == story_id)
                )
            )
            for character_mount in query:
                character_id, character_name = _story_character_identity(
                    character_mount
                )
                if character_id is None:
                    continue
                characters_by_mount[int(character_mount.id)] = (
                    models.StatusCharacterIdentity(
                        character_mount_id=int(character_mount.id),
                        character_id=character_id,
                        character_name=character_name,
                    )
                )

        candidates: list[models.StatusContextCandidate] = []
        for table in tables:
            metadata = metadata_by_table[table.id]
            referenced_mount_id = (
                metadata.story_mount.character_mount_id
                if metadata.story_mount is not None
                else None
            )
            current_mount_row = (
                mounts_by_source.get(table.source_table_id)
                if table.source_table_id is not None
                else None
            )
            current_mount = None
            if current_mount_row is not None:
                current_character_mount_id = _story_character_mount_id(
                    current_mount_row
                )
                current_mount = models.StatusStoryMountIdentity(
                    mount_id=int(current_mount_row.id),
                    mount_origin=models.validate_story_status_mount_origin(
                        str(current_mount_row.mount_origin)
                    ),
                    character=(
                        characters_by_mount.get(current_character_mount_id)
                        if current_character_mount_id is not None
                        else None
                    ),
                )
            candidates.append(
                models.StatusContextCandidate(
                    table=table,
                    referenced_character=(
                        characters_by_mount.get(referenced_mount_id)
                        if referenced_mount_id is not None
                        else None
                    ),
                    current_story_mount=current_mount,
                )
            )
        return candidates

    def update_table_metadata_for_session(
        self,
        session_id: str,
        table_id: int,
        metadata: models.SessionStatusMetadata,
    ) -> models.SessionStatusTable:
        row = self._get_session_table_row(table_id)
        if str(row.session_id) != str(session_id):
            raise FileNotFoundError(
                f"Session status table is unavailable: {session_id}/{table_id}"
            )
        row.metadata_json = models.serialize_session_status_metadata(metadata)
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        row.save()
        return _to_session_table(row)

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
        output_document = _document_from_inputs(
            document=document,
            headers=headers,
            rows=rows,
        )
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
        row.document_json = models.serialize_status_document(document.validated())
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
    ) -> models.StatusDocumentSaveResult:
        """Save a runtime document after repeating session and kind checks."""
        row = self._get_session_table_row(table_id)
        if str(row.session_id) != str(session_id):
            logger.warning(
                "rejected cross-session status table write session_id=%s table_id=%s actual_session_id=%s",
                session_id,
                table_id,
                row.session_id,
            )
            raise FileNotFoundError(
                f"Session status table is unavailable: {session_id}/{table_id}"
            )

        expected_kind = models.validate_status_kind(expected_status_kind)
        actual_kind = models.validate_status_kind(str(row.status_kind))
        if actual_kind != expected_kind:
            logger.warning(
                "rejected status table kind mismatch session_id=%s table_id=%s expected_kind=%s actual_kind=%s",
                session_id,
                table_id,
                expected_kind,
                actual_kind,
            )
            raise ValueError(
                f"Status table kind changed before write: expected {expected_kind}, got {actual_kind}"
            )

        current_document = _parse_row_document(row)
        baseline_matched = (
            base_document is None or current_document == base_document
        )
        if not baseline_matched:
            logger.warning(
                "overwriting concurrently changed status table with last-write-wins session_id=%s table_id=%s table_name=%s",
                session_id,
                table_id,
                row.name,
            )

        row.document_json = models.serialize_status_document(
            document.validated()
        )
        row.updated_at = SQL("CURRENT_TIMESTAMP")
        row.save()
        return models.StatusDocumentSaveResult(
            table=_to_session_table(row),
            baseline_matched=baseline_matched,
        )

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

    def commit_document_batch(
        self,
        session_id: str,
        document_writes: Iterable[models.StatusDocumentWrite],
        progress_writes: Iterable[models.StatusProgressWrite] = (),
    ) -> models.StatusDocumentBatchResult:
        """Atomically apply caller-prepared documents and progress values."""

        documents = tuple(document_writes)
        progress = tuple(progress_writes)
        document_ids = _unique_positive_ids(
            (write.table_id for write in documents),
            "document_writes",
        )
        progress_keys: set[tuple[int, str]] = set()
        for write in progress:
            if write.table_id <= 0:
                raise ValueError("progress table_id must be positive")
            if not write.field_key:
                raise ValueError("progress field_key must not be empty")
            if write.last_processed_turn_id <= 0:
                raise ValueError("progress turn ID must be positive")
            identity = (write.table_id, write.field_key)
            if identity in progress_keys:
                raise ValueError("progress writes contain duplicate table/key pairs")
            progress_keys.add(identity)

        affected_ids = set(document_ids) | {
            write.table_id for write in progress
        }
        if not affected_ids:
            return models.StatusDocumentBatchResult(tables=())
        rows = {
            int(row.id): row
            for row in SessionStatusTableRecord.select().where(
                SessionStatusTableRecord.id.in_(affected_ids)
            )
        }
        missing_ids = affected_ids.difference(rows)
        if missing_ids:
            raise FileNotFoundError(
                "Session status tables not found: "
                + ", ".join(str(value) for value in sorted(missing_ids))
            )
        for table_id, row in rows.items():
            if str(row.session_id) != str(session_id):
                raise FileNotFoundError(
                    f"Session status table is unavailable: {session_id}/{table_id}"
                )

        mismatches: list[int] = []
        for write in documents:
            row = rows[write.table_id]
            actual_kind = models.validate_status_kind(str(row.status_kind))
            if actual_kind != write.expected_status_kind:
                raise ValueError(
                    "Status table kind changed before document write: "
                    f"expected {write.expected_status_kind}, got {actual_kind}"
                )
            write.document.validated()
            if (
                write.base_document is not None
                and _parse_row_document(row) != write.base_document
            ):
                mismatches.append(write.table_id)
                logger.warning(
                    "overwriting concurrently changed status table with "
                    "last-write-wins session_id=%s table_id=%s",
                    session_id,
                    write.table_id,
                )

        with self._database.atomic():
            for write in documents:
                row = rows[write.table_id]
                row.document_json = models.serialize_status_document(
                    write.document.validated()
                )
                row.updated_at = SQL("CURRENT_TIMESTAMP")
                row.save()
            for write in progress:
                (
                    SessionStatusDeferredProgressRecord.insert(
                        session_status_table=write.table_id,
                        field_key=write.field_key,
                        last_processed_turn_id=write.last_processed_turn_id,
                        updated_at=SQL("CURRENT_TIMESTAMP"),
                    )
                    .on_conflict(
                        conflict_target=(
                            SessionStatusDeferredProgressRecord.session_status_table,
                            SessionStatusDeferredProgressRecord.field_key,
                        ),
                        update={
                            SessionStatusDeferredProgressRecord.last_processed_turn_id:
                                write.last_processed_turn_id,
                            SessionStatusDeferredProgressRecord.updated_at:
                                SQL("CURRENT_TIMESTAMP"),
                        },
                    )
                    .execute()
                )
        return models.StatusDocumentBatchResult(
            tables=tuple(_to_session_table(rows[table_id]) for table_id in document_ids),
            baseline_mismatch_table_ids=tuple(mismatches),
        )

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
            row.document_json = models.serialize_status_document(document.validated())
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
            current.with_data(data).validated()
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


def _parse_row_document(
    row: StatusTableTemplateRecord | SessionStatusTableRecord,
) -> models.StatusTableDocument:
    return models.parse_status_document(str(row.document_json))


def _session_metadata_for_mount(template_metadata_json: str, mount: StoryStatusTableRecord) -> str:
    metadata = models.parse_session_status_metadata(template_metadata_json)
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
    return models.serialize_session_status_metadata(
        metadata.with_story_mount(
            models.StoryStatusMountSnapshot(
                mount_id=int(mount.id),
                mount_origin=models.validate_story_status_mount_origin(
                    str(mount.mount_origin)
                ),
                character_mount_id=character_mount_id,
                character_id=character_id,
                character_name=character_name,
            )
        )
    )


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


def _story_character_identity(
    row: StoryCharacterRecord,
) -> tuple[int | None, str]:
    try:
        character = row.character
    except DoesNotExist:
        return None, ""
    return int(character.id), str(character.name or "").strip()


def _document_from_inputs(
    *,
    document: models.StatusTableDocument | None = None,
    headers: Iterable[str] = (),
    rows: Iterable[Iterable[str]] = (),
) -> models.StatusTableDocument:
    if document is not None:
        return document.validated()
    output_headers, output_rows = _materialize_table_data(headers, rows)
    data = models.StatusTableData(headers=output_headers, rows=output_rows)
    return models.StatusTableDocument.from_data(data)


def _updated_document(
    current: models.StatusTableDocument,
    *,
    document: models.StatusTableDocument | None,
    headers: Iterable[str] | None,
    rows: Iterable[Iterable[str]] | None,
) -> models.StatusTableDocument:
    if document is not None:
        return document.validated()
    if headers is None and rows is None:
        return current.validated()
    output_headers = current.headers if headers is None else tuple(str(item) for item in headers)
    output_rows = current.data_rows if rows is None else tuple(tuple(str(cell) for cell in row) for row in rows)
    return current.with_data(
        models.StatusTableData(output_headers, output_rows)
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


def _validate_name(name: str, label: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label} name must not be empty")
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"{label} name must not contain path separators: {name!r}")


def _unique_positive_ids(values: Iterable[int], label: str) -> tuple[int, ...]:
    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must contain positive integers")
        if value in seen:
            raise ValueError(f"{label} must not contain duplicate IDs")
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)
