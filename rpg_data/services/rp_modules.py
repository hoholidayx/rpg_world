"""Typed persistence boundary for Story and Session RP Module data."""

from __future__ import annotations

from typing import Mapping

from peewee import Database

from commons.types import JsonValue
from rpg_data.model.rp_modules import (
    RPModuleCatalogEntry,
    SessionRPModuleOverride,
    SessionRPModuleSelectionRows,
    StoryRPModule,
)
from rpg_data.repositories.rp_module_repo import RPModuleRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository

__all__ = ["RPModuleDataService"]


class RPModuleDataService:
    """Persist caller-selected mounts and overrides without resolving policy."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._modules = RPModuleRepository(database)
        self._stories = StoryRepository(database)
        self._sessions = SessionRepository(database)

    def list_catalog(self) -> list[RPModuleCatalogEntry]:
        return self._modules.list_catalog()

    def get_catalog(self, module_name: str) -> RPModuleCatalogEntry | None:
        return self._modules.get_catalog(str(module_name))

    def list_story_modules(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryRPModule] | None:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != str(workspace_id):
            return None
        return self._modules.list_story(int(story_id))

    def get_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
    ) -> StoryRPModule | None:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != str(workspace_id):
            return None
        return self._modules.get_story(int(story_id), str(module_name))

    def upsert_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
        *,
        enabled: bool,
        config: Mapping[str, JsonValue],
    ) -> StoryRPModule | None:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != str(workspace_id):
            return None
        if self._modules.get_catalog(str(module_name)) is None:
            raise KeyError(f"unknown RP module: {module_name}")
        with self._database.atomic():
            return self._modules.upsert_story(
                int(story_id),
                str(module_name),
                enabled=bool(enabled),
                config=config,
            )

    def get_session_selection(
        self,
        session_id: str,
    ) -> SessionRPModuleSelectionRows | None:
        session = self._sessions.get(str(session_id))
        if session is None:
            return None
        return SessionRPModuleSelectionRows(
            session=session,
            story_modules=tuple(self._modules.list_story(int(session.story_id))),
            session_overrides=tuple(self._modules.list_session(str(session_id))),
        )

    def list_session_overrides(
        self,
        session_id: str,
    ) -> list[SessionRPModuleOverride] | None:
        if self._sessions.get(str(session_id)) is None:
            return None
        return self._modules.list_session(str(session_id))

    def get_session_override(
        self,
        session_id: str,
        module_name: str,
    ) -> SessionRPModuleOverride | None:
        if self._sessions.get(str(session_id)) is None:
            return None
        return self._modules.get_session(str(session_id), str(module_name))

    def upsert_session_override(
        self,
        session_id: str,
        module_name: str,
        *,
        enabled: bool | None,
        config: Mapping[str, JsonValue],
    ) -> SessionRPModuleOverride | None:
        if self._sessions.get(str(session_id)) is None:
            return None
        if self._modules.get_catalog(str(module_name)) is None:
            raise KeyError(f"unknown RP module: {module_name}")
        with self._database.atomic():
            return self._modules.upsert_session(
                str(session_id),
                str(module_name),
                enabled=enabled,
                config=config,
            )

    def delete_session_override(
        self,
        session_id: str,
        module_name: str,
    ) -> bool | None:
        if self._sessions.get(str(session_id)) is None:
            return None
        with self._database.atomic():
            return bool(
                self._modules.delete_session(str(session_id), str(module_name))
            )
