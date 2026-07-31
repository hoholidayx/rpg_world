"""Base and turn-local tool assembly for the main Agent."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.runtime.resources import AgentContextResources
from rpg_core.agent.tools.file_tools import WriteFileTool
from rpg_core.agent.tools.history import (
    HistoryToolSet,
)
from rpg_core.agent.tools.history_query import HistoryQueryService
from rpg_core.agent.tools.lookup import LookupToolSet
from rpg_core.agent.tools.state import StateToolSet, resolve_state_tool_set
from rpg_core.agent.tools.summary import SummaryToolSet
from rpg_core.agent.tools.summary_query import SummaryQueryService
from rpg_core.agent.turn import TurnExecutionPolicy, TurnExecutionSnapshot, TurnMode
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_TOOL_NAME
from rpg_core.rp_modules.plot_scheduler.tools import PlotSandboxToolProvider
from rpg_core.scene import SCENE_TOOL_NAMES
from rpg_core.settings import settings
from rpg_core.status.tools import (
    STATUS_TABLE_EDIT_FIELDS_TOOL_NAME,
    STATUS_TABLE_SET_VALUES_TOOL_NAME,
)
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry

if TYPE_CHECKING:
    from rpg_core.rp_modules.runtime import RPModuleTurnRuntime
    from rpg_core.agent.turn.transaction import TurnScratch
    from rpg_core.rp_modules.plot_scheduler import PlotScheduleSnapshot
    from rpg_core.scene import SceneTracker
    from rpg_core.status.manager import StatusManager

_TAG = "[AgentToolService]"


class AgentToolService:
    """Build the main Agent's turn-local executable tools and schemas."""

    def __init__(
        self,
        *,
        resources: Callable[[], AgentContextResources],
        history_query: HistoryQueryService,
        summary_query: SummaryQueryService,
        extra_tools: list[BaseTool] | None = None,
        lookup_tools_enabled: bool | None = None,
        plot_sandbox_tools: PlotSandboxToolProvider | None = None,
    ) -> None:
        self._resources = resources
        if lookup_tools_enabled is None:
            lookup_tools_enabled = settings.lookup_tools_enabled
        if not isinstance(lookup_tools_enabled, bool):
            raise TypeError("lookup_tools_enabled must be a boolean")
        self._lookup_tools_enabled = lookup_tools_enabled
        self._history_tools = HistoryToolSet(history_query)
        self._summary_tools = SummaryToolSet(summary_query)
        self._lookup_tools = LookupToolSet(
            self._history_tools,
            self._summary_tools,
        )
        self._extra_tools = list(extra_tools or [])
        self._plot_sandbox_tools = plot_sandbox_tools or PlotSandboxToolProvider()
        self._base_registry: ToolRegistry | None = None

    @property
    def base_registry(self) -> ToolRegistry | None:
        return self._base_registry

    @property
    def history_tools(self) -> HistoryToolSet:
        """Standalone committed-history tools."""

        return self._history_tools

    @property
    def summary_tools(self) -> SummaryToolSet:
        """Standalone derived-Summary tools."""

        return self._summary_tools

    @property
    def lookup_tools(self) -> LookupToolSet | None:
        """Enabled lookup tools shared by main and adjudication loops."""

        return self._lookup_tools if self._lookup_tools_enabled else None

    def refresh_base_registry(self) -> None:
        registry = ToolRegistry()
        if self._lookup_tools_enabled:
            self._lookup_tools.register_into(registry)
        scene_tracker = self._resources().scene_tracker
        if scene_tracker is not None:
            registry.register_all(scene_tracker.get_tools())
        registry.register_all(self._extra_tools)
        self._base_registry = registry
        logger.info(
            _TAG + " registered {} main tool(s): {}",
            len(registry),
            [tool.name for tool in registry],
        )

    def registry_for_turn(
        self,
        scene_tracker: "SceneTracker | None",
        status_manager: "StatusManager | None",
        *,
        rp_module_runtime: "RPModuleTurnRuntime | None" = None,
        turn_execution: TurnExecutionSnapshot | None = None,
        turn_scratch: "TurnScratch | None" = None,
        plot_schedule_snapshot: "PlotScheduleSnapshot | None" = None,
    ) -> ToolRegistry | None:
        registry = ToolRegistry()
        policy = (
            turn_execution.policy
            if turn_execution is not None
            else TurnExecutionPolicy.for_mode(TurnMode.NEUTRAL)
        )
        if self._base_registry is not None:
            for tool in self._base_registry:
                if (
                    tool.name in SCENE_TOOL_NAMES
                    or tool.name in {
                        STATUS_TABLE_EDIT_FIELDS_TOOL_NAME,
                        STATUS_TABLE_SET_VALUES_TOOL_NAME,
                    }
                ):
                    continue
                if not policy.expose_state_tools and isinstance(tool, WriteFileTool):
                    continue
                registry.register(tool)
        if rp_module_runtime is not None and policy.expose_rp_modules:
            registry.register_all(rp_module_runtime.get_main_agent_tools())
        if (
            policy.expose_plot_sandbox_tools
            and turn_scratch is not None
            and plot_schedule_snapshot is not None
            and plot_schedule_snapshot.enabled
        ):
            registry.register_all(
                self._plot_sandbox_tools.get_tools(
                    plot_schedule_snapshot,
                    turn_scratch,
                )
            )
        if policy.expose_state_tools:
            registry.register_all(
                list(self.state_tools(scene_tracker, status_manager).tools)
            )
        if settings.verbose_logging:
            logger.debug(
                _TAG + " turn executable tool registry prepared: count={}, names={}",
                len(registry),
                [tool.name for tool in registry],
            )
        return registry if len(registry) else None

    @staticmethod
    def main_schemas(
        registry: ToolRegistry | None,
        *,
        rp_module_runtime: "RPModuleTurnRuntime | None",
    ) -> list[dict] | None:
        if registry is None:
            return None
        schemas = registry.get_openai_schemas()
        if rp_module_runtime is None:
            return schemas or None
        module_tool_names = {tool.name for tool in rp_module_runtime.get_tools()}
        exposed_module_tool_names = {
            tool.name for tool in rp_module_runtime.get_main_agent_tools()
        }
        filtered = [
            schema
            for schema in schemas
            if (
                str(schema.get("function", {}).get("name", ""))
                not in module_tool_names
                or str(schema.get("function", {}).get("name", ""))
                in exposed_module_tool_names
            )
        ]
        if settings.verbose_logging:
            logger.debug(
                _TAG + " main tool schema prepared: count={}, names={}",
                len(filtered),
                [
                    str(schema.get("function", {}).get("name", ""))
                    for schema in filtered
                ],
            )
        return filtered or None

    @staticmethod
    def state_tools(
        scene_tracker: "SceneTracker | None",
        status_manager: "StatusManager | None",
    ) -> StateToolSet:
        return resolve_state_tool_set(scene_tracker, status_manager)

    @staticmethod
    def narrative_outcome_tools(
        user_input: str,
        rp_module_runtime: "RPModuleTurnRuntime | None",
    ) -> list[BaseTool]:
        if rp_module_runtime is None:
            return []
        return [
            tool
            for tool in rp_module_runtime.get_status_preflight_tools(user_input)
            if tool.name == NARRATIVE_OUTCOME_TOOL_NAME
        ]
