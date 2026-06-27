"""Data manager backend provider for Play API."""

from __future__ import annotations

from pathlib import Path

from rpg_data.services import DataServiceGateway, get_data_service_gateway
from rpg_data.settings import get_database_path


class DataManagerBackend:
    """Read Play-facing metadata from the rpg_data database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._database_path = (
            Path(db_path).expanduser()
            if db_path is not None
            else get_database_path()
        )
        self._gateway: DataServiceGateway = get_data_service_gateway(self._database_path)
        self._gateway.initialize()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def close(self) -> None:
        self._gateway.close()

    async def list_workspaces(self) -> list[dict[str, object]]:
        return self._gateway.catalog.list_workspaces()

    async def list_sessions(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        return self._gateway.catalog.list_sessions(workspace, story_id)

    async def create_session(
        self,
        workspace: str,
        story_id: int,
        *,
        title: str = "",
        description: str = "",
    ) -> dict[str, object] | None:
        return self._gateway.catalog.create_session(
            workspace,
            story_id,
            title=title,
            description=description,
        )

    async def get_session(
        self,
        session_id: str,
    ) -> dict[str, object] | None:
        return self._gateway.catalog.get_session(session_id)
