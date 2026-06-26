"""Repository for workspace records."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import WorkspaceRecord, bind_database
from rpg_data.repositories._utils import get_or_none, to_workspace, update_timestamp


class WorkspaceRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        name: str,
        root_path: str,
        *,
        description: str = "",
        enabled: bool = True,
        metadata_json: str = "{}",
    ) -> models.Workspace:
        return to_workspace(WorkspaceRecord.create(
            id=workspace_id,
            name=name,
            root_path=root_path,
            description=description,
            enabled=enabled,
            metadata_json=metadata_json,
        ))

    def list(self) -> list[models.Workspace]:
        return [
            to_workspace(row)
            for row in WorkspaceRecord.select().order_by(
                WorkspaceRecord.created_at,
                WorkspaceRecord.id,
            )
        ]

    def get(self, workspace_id: str) -> models.Workspace | None:
        row = get_or_none(WorkspaceRecord, workspace_id)
        return to_workspace(row) if row is not None else None

    def update_timestamp(self, workspace_id: str) -> models.Workspace | None:
        row = update_timestamp(WorkspaceRecord, workspace_id)
        return to_workspace(row) if row is not None else None
