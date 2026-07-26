"""Combined committed-history and derived-Summary lookup capability."""

from __future__ import annotations

from rpg_core.agent.tools.history import (
    SENSITIVE_HISTORY_TOOL_NAMES,
    HistoryToolSet,
)
from rpg_core.agent.tools.summary import (
    SENSITIVE_SUMMARY_TOOL_NAMES,
    SummaryToolSet,
)
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry

SENSITIVE_LOOKUP_TOOL_NAMES = frozenset(
    SENSITIVE_HISTORY_TOOL_NAMES | SENSITIVE_SUMMARY_TOOL_NAMES
)


class LookupToolSet:
    """Expose History and Summary lookup under one shared budget boundary."""

    def __init__(
        self,
        history: HistoryToolSet,
        summaries: SummaryToolSet,
    ) -> None:
        self._history = history
        self._summaries = summaries
        self._tools = (*history.tools, *summaries.tools)
        registry = ToolRegistry()
        registry.register_all(list(self._tools))
        self._registry = registry

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        return self._tools

    @property
    def names(self) -> frozenset[str]:
        return SENSITIVE_LOOKUP_TOOL_NAMES

    def schemas(self) -> list[dict[str, object]]:
        return self._registry.get_openai_schemas()

    async def execute(self, name: str, arguments_json: str) -> str:
        if name not in self.names:
            raise PermissionError(f"{name!r} is not a lookup tool")
        return await self._registry.execute(name, arguments_json)

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register_all(list(self._tools))
