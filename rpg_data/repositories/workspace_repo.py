"""Repository for workspace records."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import Workspace, bind_database
from rpg_data.repositories._utils import get_or_none, update_timestamp


class WorkspaceRepository:
    def __init__(self, database: Database) -> None:
        self.database = bind_database(database)

    def create(
        self,
        workspace_id: str,
        name: str,
        root_path: str,
        *,
        description: str = "",
        enabled: bool = True,
        metadata_json: str = "{}",
    ) -> Workspace:
        return Workspace.create(
            id=workspace_id,
            name=name,
            root_path=root_path,
            description=description,
            enabled=enabled,
            metadata_json=metadata_json,
        )

    def list(self) -> list[Workspace]:
        return list(Workspace.select().order_by(Workspace.created_at, Workspace.id))

    def get(self, workspace_id: str) -> Workspace | None:
        return get_or_none(Workspace, workspace_id)

    def update_timestamp(self, workspace_id: str) -> Workspace | None:
        return update_timestamp(Workspace, workspace_id)

