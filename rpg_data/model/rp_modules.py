"""Typed persistence contracts for RP Module storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from commons.types import JsonValue
from rpg_data.model.session import Session


@dataclass(frozen=True)
class RPModuleCatalogEntry:
    module_name: str
    display_name: str
    description: str = ""
    sort_order: int = 0
    config_version: int = 1
    default_story_enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryRPModule:
    id: int
    story_id: int
    module_name: str
    enabled: bool = True
    config: Mapping[str, JsonValue] = field(default_factory=dict)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionRPModuleOverride:
    id: int
    session_id: str
    module_name: str
    enabled: bool | None = None
    config: Mapping[str, JsonValue] = field(default_factory=dict)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionRPModuleSelectionRows:
    """Rows needed to resolve one immutable Session RP Module snapshot."""

    session: Session
    story_modules: tuple[StoryRPModule, ...]
    session_overrides: tuple[SessionRPModuleOverride, ...]


__all__ = [
    "RPModuleCatalogEntry",
    "SessionRPModuleOverride",
    "SessionRPModuleSelectionRows",
    "StoryRPModule",
]
