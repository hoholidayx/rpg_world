"""Data manager backend provider for Play API."""

from __future__ import annotations

from pathlib import Path

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.orm import Session, Workspace, bind_database, make_database
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.settings import get_database_path


class DataManagerBackend:
    """Read Play-facing metadata from the rpg_data database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.database_path = Path(db_path).expanduser() if db_path is not None else get_database_path()
        self.database = bind_database(make_database(self.database_path))
        self._initialized = False
        self.initialize()

    def initialize(self) -> None:
        if self._initialized:
            return

        conn = db.connect(self.database_path)
        try:
            run_migrations(conn)
        finally:
            conn.close()

        self.database.connect(reuse_if_open=True)
        self._initialized = True

    def close(self) -> None:
        if not self.database.is_closed():
            self.database.close()
        self._initialized = False

    async def list_workspaces(self) -> list[dict[str, object]]:
        workspaces = [
            workspace
            for workspace in WorkspaceRepository(self.database).list()
            if workspace.enabled
        ]
        workspaces.sort(key=lambda workspace: (workspace.name, workspace.id))
        return [_workspace_summary(workspace) for workspace in workspaces]

    async def list_sessions(self, workspace: str, story_id: int) -> list[dict[str, object]] | None:
        story = StoryRepository(self.database).get(story_id)
        if story is None or str(story.workspace_id) != workspace:
            return None
        sessions = SessionRepository(self.database).list(
            workspace_id=workspace,
            story_id=story_id,
        )
        return [_session_summary(session) for session in sessions]

    async def get_session_by_locator(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
    ) -> dict[str, object] | None:
        session = SessionRepository(self.database).get_by_locator(
            workspace,
            story_id,
            session_id,
        )
        return _session_summary(session) if session is not None else None


def _workspace_summary(workspace: Workspace) -> dict[str, object]:
    description = str(workspace.description or "")
    return {
        "id": str(workspace.id),
        "name": str(workspace.name),
        "description": description or None,
    }


def _session_summary(session: Session) -> dict[str, object]:
    return {
        "id": str(session.session_key),
        "workspace": str(session.workspace_id),
        "story_id": int(session.story_id),
        "title": str(session.title or session.session_key),
        "description": None,
        "created_at": str(session.created_at),
        "updated_at": str(session.updated_at),
    }
