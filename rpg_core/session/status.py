"""Session lifecycle policy for Story-backed status-table copies."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from rpg_core.scene.status import SceneStatusService
from rpg_data.model.session import Session
from rpg_data.model.status import (
    STATUS_ORIGIN_SESSION_NATIVE,
    STATUS_ORIGIN_TEMPLATE_COPY,
    SessionStatusDocumentWrite,
    SessionStatusResetPlan,
    SessionStatusResetResult,
    SessionStatusTable,
    StoryStatusTable,
)


class SessionStatusDataPort(Protocol):
    def get_session(self, session_id: str) -> Session | None: ...

    def list_status_tables(
        self,
        session_id: str,
    ) -> list[SessionStatusTable]: ...

    def list_story_status_mounts(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryStatusTable]: ...

    def copy_story_status_mounts(
        self,
        session_id: str,
        mount_ids: Iterable[int],
    ) -> list[SessionStatusTable]: ...

    def apply_status_reset_plan(
        self,
        session_id: str,
        plan: SessionStatusResetPlan,
    ) -> SessionStatusResetResult: ...


class SessionStatusLifecycleService:
    """Choose status-table initialization and reset mutations in Core."""

    def __init__(self, data: SessionStatusDataPort) -> None:
        self._data = data

    def initialize(self, session_id: str) -> list[SessionStatusTable]:
        session = self._require_session(session_id)
        existing = self._data.list_status_tables(session.id)
        if existing:
            return existing
        mounts = self._data.list_story_status_mounts(
            session.workspace_id,
            session.story_id,
        )
        return self._data.copy_story_status_mounts(
            session.id,
            (mount.id for mount in mounts),
        )

    def reset(self, session_id: str) -> SessionStatusResetResult:
        session = self._require_session(session_id)
        existing = self._data.list_status_tables(session.id)
        template_tables = tuple(
            table
            for table in existing
            if table.origin == STATUS_ORIGIN_TEMPLATE_COPY
        )
        native_tables = tuple(
            table
            for table in existing
            if table.origin == STATUS_ORIGIN_SESSION_NATIVE
        )
        known_ids = {table.id for table in template_tables + native_tables}
        unknown = [table for table in existing if table.id not in known_ids]
        if unknown:
            raise ValueError(
                "Unsupported Session status-table origins: "
                + ", ".join(
                    f"{table.id}/{table.origin}" for table in unknown
                )
            )

        mounts = self._data.list_story_status_mounts(
            session.workspace_id,
            session.story_id,
        )
        mounted_names = {mount.table_name for mount in mounts}
        conflicts = sorted(
            table.name for table in native_tables if table.name in mounted_names
        )
        if conflicts:
            raise ValueError(
                "Session-native status table names conflict with current Story "
                "templates: "
                + ", ".join(conflicts)
            )

        plan = SessionStatusResetPlan(
            delete_table_ids=tuple(table.id for table in template_tables),
            document_writes=tuple(
                SessionStatusDocumentWrite(
                    table_id=table.id,
                    document=SceneStatusService.prepare_document(
                        table.status_kind,
                        table.document.with_cleared_values(),
                    ),
                )
                for table in native_tables
            ),
            deferred_progress_table_ids=tuple(table.id for table in existing),
            story_mount_ids=tuple(mount.id for mount in mounts),
        )
        return self._data.apply_status_reset_plan(session.id, plan)

    def _require_session(self, session_id: str) -> Session:
        session = self._data.get_session(str(session_id))
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session


__all__ = ["SessionStatusLifecycleService"]
