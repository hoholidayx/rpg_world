"""RP Module selection, inheritance, and configuration application service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from commons.types import JsonObject, JsonValue
from rpg_core.rp_modules.models import (
    ModuleCommand,
    RPModuleDefinition,
    RPModuleSelectionSnapshot,
)
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.rp_modules.runtime import RPModuleTurnRuntime
from rpg_data.model.rp_modules import (
    RPModuleCatalogEntry,
    SessionRPModuleOverride,
    SessionRPModuleSelectionRows,
    StoryRPModule,
)


class RPModuleDataPort(Protocol):
    def list_catalog(self) -> list[RPModuleCatalogEntry]: ...

    def list_story_modules(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryRPModule] | None: ...

    def get_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
    ) -> StoryRPModule | None: ...

    def upsert_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
        *,
        enabled: bool,
        config: Mapping[str, JsonValue],
    ) -> StoryRPModule | None: ...

    def get_session_selection(
        self,
        session_id: str,
    ) -> SessionRPModuleSelectionRows | None: ...

    def upsert_session_override(
        self,
        session_id: str,
        module_name: str,
        *,
        enabled: bool | None,
        config: Mapping[str, JsonValue],
    ) -> SessionRPModuleOverride | None: ...

    def delete_session_override(
        self,
        session_id: str,
        module_name: str,
    ) -> bool | None: ...


class RPModuleApplicationService:
    """Own effective RP Module policy across system, Story, and Session."""

    def __init__(self, registry: RPModuleRegistry, data: RPModuleDataPort) -> None:
        self._registry = registry
        self._data = data

    @property
    def registry(self) -> RPModuleRegistry:
        return self._registry

    def definitions(self) -> tuple[RPModuleDefinition, ...]:
        return self._registry.definitions()

    def definition(self, module_name: str) -> RPModuleDefinition | None:
        return self._registry.definition(module_name)

    def list_catalog(self) -> list[RPModuleCatalogEntry]:
        names = {definition.name for definition in self._registry.definitions()}
        return [row for row in self._data.list_catalog() if row.module_name in names]

    def resolve_snapshot(self, session_id: str) -> RPModuleSelectionSnapshot:
        resolved_session_id = str(session_id or "").strip()
        if not resolved_session_id:
            raise ValueError("session_id is required to resolve RP Modules")
        rows = self._data.get_session_selection(resolved_session_id)
        if rows is None:
            raise FileNotFoundError(f"session not found: {resolved_session_id}")
        return self._registry.build_snapshot(
            session_id=resolved_session_id,
            story_id=int(rows.session.story_id),
            mounts=rows.story_modules,
            overrides=rows.session_overrides,
        )

    def resolve_story_snapshot(
        self,
        workspace_id: str,
        story_id: int,
    ) -> RPModuleSelectionSnapshot | None:
        mounts = self._data.list_story_modules(str(workspace_id), int(story_id))
        if mounts is None:
            return None
        return self._registry.build_snapshot(
            session_id="",
            story_id=int(story_id),
            mounts=mounts,
            overrides=(),
        )

    def patch_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
        *,
        enabled: bool | None,
        config: Mapping[str, JsonValue] | None,
    ) -> RPModuleSelectionSnapshot | None:
        name = normalize_module_name(module_name)
        if self._registry.definition(name) is None:
            raise KeyError(f"unknown RP module: {name}")
        current = self._data.get_story_module(
            str(workspace_id),
            int(story_id),
            name,
        )
        if current is None:
            mounts = self._data.list_story_modules(
                str(workspace_id),
                int(story_id),
            )
            if mounts is None:
                return None
            current_enabled = True
            current_config: Mapping[str, JsonValue] = {}
        else:
            current_enabled = current.enabled
            current_config = current.config
        validated = self._validated_config(
            name,
            config if config is not None else current_config,
        )
        persisted = self._data.upsert_story_module(
            str(workspace_id),
            int(story_id),
            name,
            enabled=current_enabled if enabled is None else enabled,
            config=validated,
        )
        if persisted is None:
            return None
        return self.resolve_story_snapshot(str(workspace_id), int(story_id))

    def patch_session_override(
        self,
        session_id: str,
        module_name: str,
        *,
        enabled: bool | None,
        replace_enabled: bool,
        config: Mapping[str, JsonValue] | None,
    ) -> RPModuleSelectionSnapshot:
        name = normalize_module_name(module_name)
        if self._registry.definition(name) is None:
            raise KeyError(f"unknown RP module: {name}")
        rows = self._data.get_session_selection(str(session_id))
        if rows is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        if not any(item.module_name == name for item in rows.story_modules):
            raise ValueError(f"RP module is not mounted on Story: {name}")
        current = next(
            (item for item in rows.session_overrides if item.module_name == name),
            None,
        )
        next_enabled = (
            enabled
            if replace_enabled
            else (current.enabled if current is not None else None)
        )
        current_config: Mapping[str, JsonValue] = (
            current.config if current is not None else {}
        )
        next_config = self._validated_config(
            name,
            config if config is not None else current_config,
        )
        if next_enabled is None and not next_config:
            self._data.delete_session_override(str(session_id), name)
        else:
            persisted = self._data.upsert_session_override(
                str(session_id),
                name,
                enabled=next_enabled,
                config=next_config,
            )
            if persisted is None:
                raise FileNotFoundError(f"session not found: {session_id}")
        return self.resolve_snapshot(str(session_id))

    def clear_session_override(
        self,
        session_id: str,
        module_name: str,
    ) -> RPModuleSelectionSnapshot:
        name = normalize_module_name(module_name)
        if self._registry.definition(name) is None:
            raise KeyError(f"unknown RP module: {name}")
        deleted = self._data.delete_session_override(str(session_id), name)
        if deleted is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        return self.resolve_snapshot(str(session_id))

    def create_runtime(
        self,
        snapshot: RPModuleSelectionSnapshot,
    ) -> RPModuleTurnRuntime:
        return self._registry.create_runtime(snapshot)

    def get_commands(self, session_id: str) -> list[ModuleCommand]:
        return self._registry.commands_for_snapshot(
            self.resolve_snapshot(str(session_id))
        )

    def _validated_config(
        self,
        module_name: str,
        config: Mapping[str, JsonValue],
    ) -> JsonObject:
        return self._registry.validate_config_patch(module_name, config)


def normalize_module_name(value: str) -> str:
    name = str(value or "").strip().lower()
    if not name:
        raise ValueError("module_name must not be empty")
    return name


__all__ = [
    "RPModuleApplicationService",
    "RPModuleDataPort",
    "normalize_module_name",
]
