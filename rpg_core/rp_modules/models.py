"""Shared models for RP Modules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from rpg_core.context import RPModuleRuntimeSection

ModuleCommandHandler = Callable[[object, list[str]], Awaitable[str]]


@dataclass(frozen=True)
class ModuleContextRequest:
    """Inputs used by modules that expose dynamic runtime sections."""

    session_id: str
    user_input: str = ""
    include_staged_turn: bool = False
    """Whether runtime sections may expose scratch data from the active turn."""


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


@dataclass(frozen=True)
class RPModuleDefinition:
    """Static metadata and config contract for one built-in Python module."""

    name: str
    display_name: str
    description: str
    sort_order: int
    configurable_fields: tuple[str, ...]
    config_validator: Callable[[Mapping[str, object]], dict[str, object]] = field(
        repr=False,
        compare=False,
    )
    system_config_resolver: Callable[[object], tuple[bool, dict[str, object]]] = field(
        repr=False,
        compare=False,
    )
    module_factory: Callable[..., object] = field(repr=False, compare=False)


@dataclass(frozen=True)
class RPModuleSelection:
    """One module's immutable effective Story/Session selection."""

    name: str
    display_name: str
    description: str
    sort_order: int
    system_enabled: bool
    story_mounted: bool
    story_enabled: bool
    session_enabled_override: bool | None
    effective_enabled: bool
    system_config: Mapping[str, object]
    story_config: Mapping[str, object]
    session_config: Mapping[str, object]
    effective_config: Mapping[str, object]
    config_sources: Mapping[str, str]

    def __post_init__(self) -> None:
        for field_name in (
            "system_config",
            "story_config",
            "session_config",
            "effective_config",
            "config_sources",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_mapping(getattr(self, field_name)),
            )


@dataclass(frozen=True)
class RPModuleSelectionSnapshot:
    """Immutable RP Module capability/config snapshot for one preview or turn."""

    session_id: str
    story_id: int
    global_enabled: bool
    modules: tuple[RPModuleSelection, ...]

    def get(self, module_name: str) -> RPModuleSelection | None:
        return next((module for module in self.modules if module.name == module_name), None)

    @property
    def enabled_modules(self) -> tuple[RPModuleSelection, ...]:
        return tuple(module for module in self.modules if module.effective_enabled)


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    return value
