"""Turn-local RP Module instances created from an immutable selection snapshot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.tooling.base import BaseTool
from rpg_core.context import FixedLayerSection, RPModuleRuntimeSection
from rpg_core.rp_modules.base import RPModule
from rpg_core.rp_modules.constants import RP_MODULE_NARRATIVE_OUTCOME_NAME
from rpg_core.rp_modules.models import ModuleContextRequest, RPModuleSelectionSnapshot
from rpg_core.rp_modules.narrative_outcome import NarrativeOutcomeModule

if TYPE_CHECKING:
    from rpg_core.agent.turn.transaction import TurnScratch


class RPModuleTurnRuntime:
    """Own module instances and tool bindings for one turn or context preview."""

    def __init__(
        self,
        snapshot: RPModuleSelectionSnapshot,
        modules: list[RPModule],
    ) -> None:
        self.snapshot = snapshot
        self._modules = {module.name: module for module in modules}
        self._bound_scratch: TurnScratch | None = None
        self._validate_tool_names()

    def enabled_modules(self) -> list[RPModule]:
        return [self._modules[name] for name in sorted(self._modules)]

    def get_fixed_sections(self) -> list[FixedLayerSection]:
        sections: list[FixedLayerSection] = []
        for module in self.enabled_modules():
            sections.extend(module.get_fixed_sections())
        return sorted(sections, key=lambda section: (section.priority, section.id))

    def get_runtime_sections(
        self,
        request: ModuleContextRequest,
    ) -> list[RPModuleRuntimeSection]:
        sections: list[RPModuleRuntimeSection] = []
        for module in self.enabled_modules():
            sections.extend(module.get_runtime_sections(request))
        return sorted(sections, key=lambda section: (section.priority, section.id))

    def get_tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = []
        for module in self.enabled_modules():
            tools.extend(module.get_tools())
        return tools

    def get_main_agent_tools(self) -> list[BaseTool]:
        """Return turn-sensitive tools exposed to the main Agent."""
        tools: list[BaseTool] = []
        for module in self.enabled_modules():
            tools.extend(module.get_main_agent_tools())
        return tools

    def get_status_preflight_tools(self, user_input: str) -> list[BaseTool]:
        module = self._modules.get(RP_MODULE_NARRATIVE_OUTCOME_NAME)
        if not isinstance(module, NarrativeOutcomeModule):
            return []
        if not module.should_offer_status_preflight(user_input):
            return []
        return module.get_tools()

    def get_module(self, name: str) -> RPModule | None:
        return self._modules.get(name)

    def bind_turn(self, scratch: TurnScratch) -> None:
        if self._bound_scratch is not None:
            raise RuntimeError("RP Module runtime is already bound")
        self._bound_scratch = scratch
        scratch.rp_module_snapshot = self.snapshot
        scratch.rp_module_runtime = self
        for module in self.enabled_modules():
            module.bind_turn(scratch)

    def close(self) -> None:
        scratch = self._bound_scratch
        if scratch is None:
            return
        for module in reversed(self.enabled_modules()):
            module.unbind_turn(scratch)
        if scratch.rp_module_runtime is self:
            scratch.rp_module_runtime = None
        self._bound_scratch = None

    def _validate_tool_names(self) -> None:
        owners: dict[str, str] = {}
        for module in self.enabled_modules():
            for tool in module.get_tools():
                owner = owners.get(tool.name)
                if owner is not None:
                    raise ValueError(
                        f"Duplicate RP module tool name {tool.name!r}: {owner} and {module.name}"
                    )
                owners[tool.name] = module.name
