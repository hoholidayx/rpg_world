"""Story RP Module mounts and Session override persistence."""

from __future__ import annotations

from typing import Mapping

from peewee import Database

from rpg_data import models
from rpg_data.repositories.rp_module_repo import RPModuleRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository

__all__ = ["RPModuleService"]


class RPModuleService:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._modules = RPModuleRepository(database)
        self._stories = StoryRepository(database)
        self._sessions = SessionRepository(database)

    def list_catalog(self) -> list[models.RPModuleCatalogEntry]:
        return self._modules.list_catalog()

    def get_catalog(self, module_name: str) -> models.RPModuleCatalogEntry | None:
        return self._modules.get_catalog(_module_name(module_name))

    def mount_story_defaults(self, story_id: int) -> list[models.StoryRPModule]:
        if self._stories.get(int(story_id)) is None:
            raise FileNotFoundError(f"story not found: {story_id}")
        return self._modules.mount_story_defaults(int(story_id))

    def list_story_modules(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryRPModule] | None:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != workspace_id:
            return None
        return self._modules.list_story(int(story_id))

    def get_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
    ) -> models.StoryRPModule | None:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != workspace_id:
            return None
        return self._modules.get_story(int(story_id), _module_name(module_name))

    def set_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
        *,
        enabled: bool,
        config: Mapping[str, object],
    ) -> models.StoryRPModule | None:
        name = _module_name(module_name)
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != workspace_id:
            return None
        if self._modules.get_catalog(name) is None:
            raise KeyError(f"unknown RP module: {name}")
        with self._database.atomic():
            return self._modules.upsert_story(
                int(story_id),
                name,
                enabled=bool(enabled),
                config=config,
            )

    def list_session_overrides(
        self,
        session_id: str,
    ) -> list[models.SessionRPModuleOverride] | None:
        if self._sessions.get(session_id) is None:
            return None
        return self._modules.list_session(session_id)

    def get_session_override(
        self,
        session_id: str,
        module_name: str,
    ) -> models.SessionRPModuleOverride | None:
        if self._sessions.get(session_id) is None:
            return None
        return self._modules.get_session(session_id, _module_name(module_name))

    def set_session_override(
        self,
        session_id: str,
        module_name: str,
        *,
        enabled: bool | None,
        config: Mapping[str, object],
    ) -> models.SessionRPModuleOverride | None:
        name = _module_name(module_name)
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if self._modules.get_story(int(session.story_id), name) is None:
            raise KeyError(f"RP module is not mounted on Story: {name}")
        with self._database.atomic():
            if enabled is None and not config:
                self._modules.delete_session(session_id, name)
                return None
            return self._modules.upsert_session(
                session_id,
                name,
                enabled=enabled,
                config=config,
            )

    def clear_session_override(self, session_id: str, module_name: str) -> bool | None:
        if self._sessions.get(session_id) is None:
            return None
        with self._database.atomic():
            return bool(self._modules.delete_session(session_id, _module_name(module_name)))


def _module_name(value: str) -> str:
    name = str(value or "").strip().lower()
    if not name:
        raise ValueError("module_name must not be empty")
    return name
