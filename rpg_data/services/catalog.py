"""Read-facing catalog service for external modules."""

from __future__ import annotations

import logging
from pathlib import Path

from peewee import Database

from rpg_data import models
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services.status import StatusTableService
from rpg_data.settings import resolve_workspace_relative_path, resolve_workspace_root

__all__ = ["CatalogService"]

logger = logging.getLogger("rpg_data.catalog")

_WorkspaceSummary = dict[str, object]
_SessionSummary = dict[str, object]


class CatalogService:
    """Expose workspace/story/session metadata without leaking repositories."""

    def __init__(
        self,
        database: Database,
        *,
        status_service: StatusTableService | None = None,
    ) -> None:
        self._database = database
        self._workspaces = WorkspaceRepository(database)
        self._stories = StoryRepository(database)
        self._sessions = SessionRepository(database)
        self._status = status_service

    def list_workspaces(self) -> list[_WorkspaceSummary]:
        workspaces = [
            workspace
            for workspace in self._workspaces.list()
            if workspace.enabled
        ]
        workspaces.sort(key=lambda workspace: (workspace.name, workspace.id))
        result = [_workspace_summary(workspace) for workspace in workspaces]
        logger.debug("listed workspaces count=%s ids=%s", len(result), [item["id"] for item in result])
        return result

    def list_sessions(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[_SessionSummary] | None:
        story = self._stories.get(story_id)
        if story is None or story.workspace_id != workspace_id:
            logger.warning("list sessions rejected missing story workspace_id=%s story_id=%s", workspace_id, story_id)
            return None
        sessions = self._sessions.list(
            workspace_id=workspace_id,
            story_id=story_id,
        )
        result = [_session_summary(session) for session in sessions]
        logger.debug(
            "listed sessions workspace_id=%s story_id=%s count=%s session_ids=%s",
            workspace_id,
            story_id,
            len(result),
            [item["id"] for item in result],
        )
        return result

    def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        session_id: str | None = None,
        title: str = "",
        description: str = "",
    ) -> _SessionSummary | None:
        story = self._stories.get(story_id)
        if story is None or story.workspace_id != workspace_id:
            logger.warning("create session rejected missing story workspace_id=%s story_id=%s", workspace_id, story_id)
            return None
        logger.info("creating session workspace_id=%s story_id=%s title=%s", workspace_id, story_id, title)
        with self._database.atomic():
            session = self._sessions.create(
                workspace_id,
                story_id,
                session_id=session_id,
                title=title,
                description=description,
            )
            if self._status is not None:
                tables = self._status.initialize_session_tables(session.id)
                logger.info(
                    "initialized session status tables session_id=%s table_count=%s",
                    session.id,
                    len(tables),
                )
        result = _session_summary(session)
        logger.info("created session session_id=%s workspace_id=%s story_id=%s", session.id, workspace_id, story_id)
        return result

    def get_session(
        self,
        session_id: str,
    ) -> _SessionSummary | None:
        session = self._sessions.get(session_id)
        if session is None:
            logger.debug("session not found session_id=%s", session_id)
            return None
        logger.debug(
            "loaded session session_id=%s workspace_id=%s story_id=%s",
            session_id,
            session.workspace_id,
            session.story_id,
        )
        return _session_summary(session)

    def get_workspace_runtime_dir(self, workspace_id: str) -> Path:
        """Return the resolved catalog workspace root directory."""

        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise FileNotFoundError(f"Workspace not found in rpg_data: {workspace_id}")
        path = resolve_workspace_root(workspace.root_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_session_workspace_dir(self, session_id: str) -> Path:
        """Return the resolved workspace root for the session's workspace."""

        session = self._sessions.get(session_id)
        if session is None:
            raise FileNotFoundError(f"Session not found in rpg_data: {session_id}")
        return self.get_workspace_runtime_dir(session.workspace_id)

    def get_session_runtime_dir(self, session_id: str) -> Path:
        """Return the catalog-owned runtime directory for a session.

        Session-scoped runtime files live under the story-bound session root:
        ``{workspace_root}/stories/{story_id}/{session_id}``.
        """

        session = self._sessions.get(session_id)
        if session is None:
            raise FileNotFoundError(f"Session not found in rpg_data: {session_id}")
        workspace_root = self.get_workspace_runtime_dir(session.workspace_id)
        path = resolve_workspace_relative_path(
            workspace_root,
            _session_runtime_relative_path(int(session.story_id), str(session.id)),
        )
        path.mkdir(parents=True, exist_ok=True)
        return path


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


def _session_runtime_relative_path(story_id: int, session_id: str) -> str:
    return f"stories/{story_id}/{session_id}"
