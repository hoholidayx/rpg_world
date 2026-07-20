"""Session lifecycle policy for Story-backed status-table copies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_data import models as data_models

if TYPE_CHECKING:
    from rpg_data.services.gateway import DataServiceGateway


class SessionStatusLifecycleService:
    """Choose status-table initialization and reset mutations in Core."""

    def __init__(self, gateway: "DataServiceGateway") -> None:
        self._gateway = gateway

    def initialize(self, session_id: str) -> list[data_models.SessionStatusTable]:
        session = self._require_session(session_id)
        existing = self._gateway.status.list_tables(session.id)
        if existing:
            return existing
        mounts = self._gateway.status.list_story_mounts(
            session.workspace_id,
            session.story_id,
        )
        return self._gateway.status.copy_story_mounts_to_session(
            session.id,
            (mount.id for mount in mounts),
        )

    def reset(self, session_id: str) -> data_models.SessionStatusResetResult:
        session = self._require_session(session_id)
        existing = self._gateway.status.list_tables(session.id)
        template_tables = tuple(
            table
            for table in existing
            if table.origin == data_models.STATUS_ORIGIN_TEMPLATE_COPY
        )
        native_tables = tuple(
            table
            for table in existing
            if table.origin == data_models.STATUS_ORIGIN_SESSION_NATIVE
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

        mounts = self._gateway.status.list_story_mounts(
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

        plan = data_models.SessionStatusResetPlan(
            delete_table_ids=tuple(table.id for table in template_tables),
            document_writes=tuple(
                data_models.SessionStatusDocumentWrite(
                    table_id=table.id,
                    document=table.document.with_cleared_values(),
                )
                for table in native_tables
            ),
            deferred_progress_table_ids=tuple(table.id for table in existing),
            story_mount_ids=tuple(mount.id for mount in mounts),
        )
        return self._gateway.status.apply_session_reset_plan(session.id, plan)

    def _require_session(self, session_id: str) -> data_models.Session:
        session = self._gateway.catalog.get_session(str(session_id))
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session


__all__ = ["SessionStatusLifecycleService"]
