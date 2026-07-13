"""Base and turn-local tool assembly for the main Agent."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.resources import AgentContextResources
from rpg_core.agent.tools import (
    BaseTool,
    GrepTool,
    ListFilesTool,
    ReadFileTool,
    ToolRegistry,
    WriteFileTool,
)
from rpg_core.agent.transaction import SCENE_TOOL_NAMES
from rpg_core.agent.turn import TurnExecutionPolicy, TurnExecutionSnapshot, TurnMode
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_TOOL_NAME
from rpg_core.settings import settings
from rpg_core.status.tools import (
    STATUS_TABLE_SET_VALUES_TOOL_NAME,
    StatusTableToolProvider,
)

if TYPE_CHECKING:
    from rpg_core.rp_modules import RPModuleTurnRuntime
    from rpg_core.scene import SceneTracker
    from rpg_core.status.manager import StatusManager

_TAG = "[AgentToolService]"


class AgentToolService:
    """Build the main Agent's turn-local executable tools and schemas."""

    def __init__(
        self,
        *,
        session_id: Callable[[], str],
        resources: Callable[[], AgentContextResources],
        extra_tools: list[BaseTool] | None = None,
    ) -> None:
        self._session_id = session_id
        self._resources = resources
        self._extra_tools = list(extra_tools or [])
        self._base_registry: ToolRegistry | None = None

    @property
    def base_registry(self) -> ToolRegistry | None:
        return self._base_registry

    def refresh_base_registry(self) -> None:
        from rpg_core.agent.tools.file_tools import FileToolSandbox
        from rpg_data.services import get_data_service_gateway

        session_root = get_data_service_gateway().catalog.get_session_runtime_dir(
            self._session_id()
        )
        sandbox = FileToolSandbox(session_root=session_root)
        registry = ToolRegistry()
        registry.register_all(
            [
                ListFilesTool(sandbox),
                ReadFileTool(sandbox),
                WriteFileTool(sandbox),
                GrepTool(sandbox),
            ]
        )
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
    ) -> ToolRegistry | None:
        registry = ToolRegistry()
        policy = (
            turn_execution.policy
            if turn_execution is not None
            else TurnExecutionPolicy.for_mode(TurnMode.IC)
        )
        if self._base_registry is not None:
            for tool in self._base_registry:
                if (
                    tool.name in SCENE_TOOL_NAMES
                    or tool.name == STATUS_TABLE_SET_VALUES_TOOL_NAME
                ):
                    continue
                if not policy.expose_state_tools and isinstance(tool, WriteFileTool):
                    continue
                registry.register(tool)
        if rp_module_runtime is not None and policy.expose_rp_modules:
            registry.register_all(rp_module_runtime.get_main_agent_tools())
        if policy.expose_state_tools:
            registry.register_all(self.state_tools(scene_tracker, status_manager))
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
    ) -> list[BaseTool]:
        tools: list[BaseTool] = []
        if scene_tracker is not None:
            tools.extend(scene_tracker.get_tools())
        if status_manager is not None:
            tools.extend(StatusTableToolProvider(status_manager).get_tools())
        return tools

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
