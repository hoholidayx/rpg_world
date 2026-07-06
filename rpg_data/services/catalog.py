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

    def list_workspaces(self) -> list[models.Workspace]:
        workspaces = [
            workspace
            for workspace in self._workspaces.list()
            if workspace.enabled
        ]
        workspaces.sort(key=lambda workspace: (workspace.name, workspace.id))
        logger.debug("listed workspaces count=%s ids=%s", len(workspaces), [workspace.id for workspace in workspaces])
        return workspaces

    def list_sessions(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.Session] | None:
        story = self._stories.get(story_id)
        if story is None or story.workspace_id != workspace_id:
            logger.warning("list sessions rejected missing story workspace_id=%s story_id=%s", workspace_id, story_id)
            return None
        sessions = self._sessions.list(
            workspace_id=workspace_id,
            story_id=story_id,
        )
        logger.debug(
            "listed sessions workspace_id=%s story_id=%s count=%s session_ids=%s",
            workspace_id,
            story_id,
            len(sessions),
            [session.id for session in sessions],
        )
        return sessions

    def list_stories(self, workspace_id: str) -> list[models.Story] | None:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            logger.warning("list stories rejected missing workspace_id=%s", workspace_id)
            return None
        stories = self._stories.list(workspace_id)
        logger.debug(
            "listed stories workspace_id=%s count=%s story_ids=%s",
            workspace_id,
            len(stories),
            [story.id for story in stories],
        )
        return stories

    def create_story(
        self,
        workspace_id: str,
        *,
        title: str,
        summary: str = "",
        story_prompt: str = "",
        first_message: str = "",
    ) -> models.Story | None:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            logger.warning("create story rejected missing workspace_id=%s", workspace_id)
            return None
        logger.info("creating story workspace_id=%s title=%s", workspace_id, title)
        with self._database.atomic():
            story = self._stories.create(
                workspace_id,
                title,
                summary=summary,
                story_prompt=story_prompt,
                first_message=first_message,
            )
        logger.info("created story story_id=%s workspace_id=%s", story.id, workspace_id)
        return story

    def update_story(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        story_prompt: str | None = None,
        first_message: str | None = None,
    ) -> models.Story | None:
        story = self._stories.get(story_id)
        if story is None or story.workspace_id != workspace_id:
            logger.warning("update story rejected missing story workspace_id=%s story_id=%s", workspace_id, story_id)
            return None
        logger.info("updating story workspace_id=%s story_id=%s", workspace_id, story_id)
        with self._database.atomic():
            return self._stories.update(
                story_id,
                title=title,
                summary=summary,
                story_prompt=story_prompt,
                first_message=first_message,
            )

    def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        session_id: str | None = None,
        title: str = "",
        description: str = "",
        player_character_id: int | None = None,
        player_character_snapshot_json: str = "{}",
    ) -> models.Session | None:
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
                player_character_id=player_character_id,
                player_character_snapshot_json=player_character_snapshot_json,
            )
            if self._status is not None:
                tables = self._status.initialize_session_tables(session.id)
                logger.info(
                    "initialized session status tables session_id=%s table_count=%s",
                    session.id,
                    len(tables),
                )
        logger.info("created session session_id=%s workspace_id=%s story_id=%s", session.id, workspace_id, story_id)
        return session

    def get_session(
        self,
        session_id: str,
    ) -> models.Session | None:
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
        return session

    def get_session_story(
        self,
        session_id: str,
    ) -> models.Story | None:
        session = self._sessions.get(session_id)
        if session is None:
            logger.debug("session story not found session_id=%s", session_id)
            return None
        story = self._stories.get(session.story_id)
        if story is None or story.workspace_id != session.workspace_id:
            logger.warning(
                "session story rejected inconsistent catalog session_id=%s workspace_id=%s story_id=%s",
                session_id,
                session.workspace_id,
                session.story_id,
            )
            return None
        logger.debug(
            "loaded session story session_id=%s workspace_id=%s story_id=%s",
            session_id,
            story.workspace_id,
            story.id,
        )
        return story

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


def _session_runtime_relative_path(story_id: int, session_id: str) -> str:
    return f"stories/{story_id}/{session_id}"
