"""Read-facing catalog service for external modules."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository

__all__ = ["CatalogService"]


_WorkspaceSummary = dict[str, object]
_SessionSummary = dict[str, object]


class CatalogService:
    """Expose workspace/story/session metadata without leaking repositories."""

    def __init__(self, database: Database) -> None:
        self._workspaces = WorkspaceRepository(database)
        self._stories = StoryRepository(database)
        self._sessions = SessionRepository(database)

    def list_workspaces(self) -> list[_WorkspaceSummary]:
        workspaces = [
            workspace
            for workspace in self._workspaces.list()
            if workspace.enabled
        ]
        workspaces.sort(key=lambda workspace: (workspace.name, workspace.id))
        return [_workspace_summary(workspace) for workspace in workspaces]

    def list_sessions(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[_SessionSummary] | None:
        story = self._stories.get(story_id)
        if story is None or story.workspace_id != workspace_id:
            return None
        sessions = self._sessions.list(
            workspace_id=workspace_id,
            story_id=story_id,
        )
        return [_session_summary(session) for session in sessions]

    def get_session_by_locator(
        self,
        workspace_id: str,
        story_id: int,
        session_key: str,
    ) -> _SessionSummary | None:
        session = self._sessions.get_by_locator(
            workspace_id,
            story_id,
            session_key,
        )
        return _session_summary(session) if session is not None else None


def _workspace_summary(workspace: models.Workspace) -> _WorkspaceSummary:
    description = str(workspace.description or "")
    return {
        "id": str(workspace.id),
        "name": str(workspace.name),
        "description": description or None,
    }


def _session_summary(session: models.Session) -> _SessionSummary:
    return {
        "id": str(session.session_key),
        "workspace": str(session.workspace_id),
        "story_id": int(session.story_id),
        "title": str(session.title or session.session_key),
        "description": None,
        "created_at": str(session.created_at),
        "updated_at": str(session.updated_at),
    }
