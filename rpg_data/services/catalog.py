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

    def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str = "",
        description: str = "",
    ) -> _SessionSummary | None:
        story = self._stories.get(story_id)
        if story is None or story.workspace_id != workspace_id:
            return None
        session = self._sessions.create(
            workspace_id,
            story_id,
            title=title,
            description=description,
        )
        return _session_summary(session)

    def get_session(
        self,
        session_id: str,
    ) -> _SessionSummary | None:
        session = self._sessions.get(session_id)
        return _session_summary(session) if session is not None else None


def _workspace_summary(workspace: models.Workspace) -> _WorkspaceSummary:
    description = str(workspace.description or "")
    return {
        "id": str(workspace.id),
        "name": str(workspace.name),
        "description": description or None,
    }


def _session_summary(session: models.Session) -> _SessionSummary:
    # 对外只暴露全局 session id；workspace/story 作为已绑定上下文返回给 Play API 使用。
    return {
        "id": str(session.id),
        "workspace": str(session.workspace_id),
        "story_id": int(session.story_id),
        "title": str(session.title or session.id),
        "description": str(session.description or "") or None,
        "created_at": str(session.created_at),
        "updated_at": str(session.updated_at),
    }
