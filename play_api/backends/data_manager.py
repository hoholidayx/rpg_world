"""Data manager backend provider for Play API."""

from __future__ import annotations

from pathlib import Path

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.services.catalog import CatalogService
from rpg_data.settings import get_database_path


class DataManagerBackend:
    """Read Play-facing metadata from the rpg_data database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._database_path = (
            Path(db_path).expanduser()
            if db_path is not None
            else get_database_path()
        )
        self._database = db.bind_peewee_database(
            db.make_peewee_database(self._database_path)
        )
        self._catalog = CatalogService(self._database)
        self._initialized = False
        self._initialize()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def _initialize(self) -> None:
        if self._initialized:
            return

        conn = db.connect(self._database_path)
        try:
            run_migrations(conn)
        finally:
            conn.close()

        self._database.connect(reuse_if_open=True)
        self._initialized = True

    def close(self) -> None:
        if not self._database.is_closed():
            self._database.close()
        self._initialized = False

    async def list_workspaces(self) -> list[dict[str, object]]:
        return self._catalog.list_workspaces()

    async def list_sessions(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        return self._catalog.list_sessions(workspace, story_id)

    async def get_session_by_locator(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
    ) -> dict[str, object] | None:
        return self._catalog.get_session_by_locator(
            workspace,
            story_id,
            session_id,
        )
