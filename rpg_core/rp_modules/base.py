"""Base interface for RP Modules."""

from __future__ import annotations

from abc import ABC

from rpg_core.agent.tools import BaseTool
from rpg_core.context import FixedLayerSection, RPModuleRuntimeSection
from rpg_core.rp_modules.models import (
    ModuleActivationEvent,
    ModuleCommand,
    ModuleContextRequest,
    ModuleToolResultEvent,
)


class RPModule(ABC):
    """A RP-specific gameplay module.

    MVP modules are intentionally small: stable fixed-layer contract,
    optional runtime sections, tools and slash commands.
    """

    name: str = ""

    def get_fixed_sections(self) -> list[FixedLayerSection]:
        return []

    def get_runtime_sections(self, request: ModuleContextRequest) -> list[RPModuleRuntimeSection]:
        del request
        return []

    def get_tools(self) -> list[BaseTool]:
        return []

    def get_commands(self) -> list[ModuleCommand]:
        return []

    def on_module_activated(self, event: ModuleActivationEvent) -> None:
        del event

    def on_module_deactivated(self, event: ModuleActivationEvent) -> None:
        del event

    def on_other_module_activated(self, event: ModuleActivationEvent) -> None:
        del event

    def on_other_module_deactivated(self, event: ModuleActivationEvent) -> None:
        del event

    def on_module_tool_result(self, event: ModuleToolResultEvent) -> None:
        del event
