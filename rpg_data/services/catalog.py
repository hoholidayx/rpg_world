"""Read-facing catalog service for external modules."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from peewee import Database

from rpg_data import models
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.rp_module_repo import RPModuleRepository
from rpg_data.repositories.session_composer_repo import SessionComposerRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services.status import StatusTableService
from rpg_data.settings import resolve_workspace_relative_path, resolve_workspace_root
from rpg_data.story_template import validate_story_text_template

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
        self._rp_modules = RPModuleRepository(database)
        self._session_composer = SessionComposerRepository(database)
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
            lifecycle=models.SESSION_LIFECYCLE_READY,
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

    def get_story(
        self,
        workspace_id: str,
        story_id: int,
    ) -> models.Story | None:
        story = self._stories.get(story_id)
        if story is None or story.workspace_id != workspace_id:
            return None
        return story

    def create_story(
        self,
        workspace_id: str,
        *,
        title: str,
        summary: str = "",
        story_prompt: str = "",
        openings: Sequence[models.StoryOpeningInput] = (),
    ) -> models.Story | None:
        validate_story_text_template(story_prompt)
        normalized_openings = _normalize_story_openings(openings)
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
                openings=normalized_openings,
            )
            self._rp_modules.mount_story_defaults(story.id)
            self._session_composer.mount_all_workspace_styles(workspace_id, story.id)
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
        openings: Sequence[models.StoryOpeningInput] | None = None,
    ) -> models.Story | None:
        if story_prompt is not None:
            validate_story_text_template(story_prompt)
        normalized_openings = (
            _normalize_story_openings(openings)
            if openings is not None
            else None
        )
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
                openings=normalized_openings,
            )

    def list_story_openings(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryOpening] | None:
        story = self.get_story(workspace_id, story_id)
        return list(story.openings) if story is not None else None

    def set_story_main_llm_provider_key(
        self,
        workspace_id: str,
        story_id: int,
        provider_key: str | None,
    ) -> models.Story | None:
        story = self.get_story(workspace_id, story_id)
        if story is None:
            return None
        with self._database.atomic():
            return self._stories.set_main_llm_provider_key(story_id, provider_key)

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

    def set_session_main_llm_provider_key(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> models.Session | None:
        if self._sessions.get(session_id) is None:
            return None
        return self._sessions.set_main_llm_provider_key(session_id, provider_key)

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

    def resolve_session_runtime_dir(self, session_id: str) -> Path:
        """Resolve a session runtime path without creating any directories."""

        session = self._sessions.get(session_id)
        if session is None:
            raise FileNotFoundError(f"Session not found in rpg_data: {session_id}")
        workspace = self._workspaces.get(session.workspace_id)
        if workspace is None:
            raise FileNotFoundError(
                f"Workspace not found in rpg_data: {session.workspace_id}"
            )
        workspace_root = resolve_workspace_root(workspace.root_path)
        return resolve_workspace_relative_path(
            workspace_root,
            _session_runtime_relative_path(int(session.story_id), str(session.id)),
        )

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

        path = self.resolve_session_runtime_dir(session_id)
        path.mkdir(parents=True, exist_ok=True)
        return path


def _session_runtime_relative_path(story_id: int, session_id: str) -> str:
    return f"stories/{story_id}/{session_id}"


def _normalize_story_openings(
    openings: Sequence[models.StoryOpeningInput],
) -> tuple[models.StoryOpeningInput, ...]:
    if len(openings) > models.MAX_STORY_OPENINGS:
        raise ValueError(
            f"story supports at most {models.MAX_STORY_OPENINGS} openings"
        )
    normalized: list[models.StoryOpeningInput] = []
    titles: set[str] = set()
    ids: set[int] = set()
    for item in openings:
        opening_id = item.id
        if opening_id is not None:
            if isinstance(opening_id, bool) or int(opening_id) <= 0:
                raise ValueError("story opening id must be a positive integer")
            opening_id = int(opening_id)
            if opening_id in ids:
                raise ValueError(f"duplicate story opening id: {opening_id}")
            ids.add(opening_id)
        title = str(item.title or "").strip()
        message = str(item.message or "").strip()
        if not title:
            raise ValueError("story opening title must not be empty")
        if not message:
            raise ValueError("story opening message must not be empty")
        if title in titles:
            raise ValueError(f"duplicate story opening title: {title}")
        titles.add(title)
        validate_story_text_template(message)
        normalized.append(models.StoryOpeningInput(
            id=opening_id,
            title=title,
            message=message,
        ))
    return tuple(normalized)
