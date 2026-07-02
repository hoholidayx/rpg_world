"""Shared models for RP Modules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from rpg_core.context import RPModuleRuntimeSection

ModuleCommandHandler = Callable[[Any, list[str]], Awaitable[str]]


@dataclass(frozen=True)
class ModuleContextRequest:
    """Inputs used by modules that expose dynamic runtime sections."""

    session_id: str
    user_input: str = ""


@dataclass(frozen=True)
class ModuleCommand:
    """Slash command exposed by an RP module or the module registry."""

    name: str
    description: str
    detail: str
    handler: ModuleCommandHandler


@dataclass(frozen=True)
class ModuleStatus:
    """Small status snapshot for command output and tests."""

    name: str
    enabled: bool
    tools: tuple[str, ...] = ()
    fixed_section_ids: tuple[str, ...] = ()
    config_summary: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ModuleActivationEvent:
    """Reserved hook event for future cross-module coordination."""

    module_name: str
    active_modules: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class ModuleToolResultEvent:
    """Reserved hook event fired after module-owned tools complete."""

    module_name: str
    tool_name: str
    result: str


RuntimeSections = list[RPModuleRuntimeSection]
