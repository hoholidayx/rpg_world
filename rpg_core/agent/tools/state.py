"""Unified discovery of turn-local scene and normal status tools."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rpg_core.tooling.base import BaseTool
from rpg_core.scene.tools import SCENE_TOOL_NAMES
from rpg_core.status.tools import (
    STATUS_TABLE_SET_VALUES_TOOL_NAME,
    StatusTableToolProvider,
)

if TYPE_CHECKING:
    from rpg_core.scene import SceneTracker
    from rpg_core.status.manager import StatusManager


STATE_TOOL_NAMES = frozenset({
    *SCENE_TOOL_NAMES,
    STATUS_TABLE_SET_VALUES_TOOL_NAME,
})


@dataclass(frozen=True)
class StateToolSet:
    """Immutable view of the state tools actually exposed for one runtime."""

    tools: tuple[BaseTool, ...] = ()
    names: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        names = tuple(tool.name for tool in self.tools)
        if len(names) != len(set(names)):
            raise ValueError("Duplicate state tool name")
        object.__setattr__(self, "names", names)

    @classmethod
    def from_tools(cls, tools: Iterable[BaseTool]) -> "StateToolSet":
        """Keep only known state tools while preserving registration order."""
        return cls(tuple(tool for tool in tools if tool.name in STATE_TOOL_NAMES))

    def supports(self, name: str) -> bool:
        return name in self.names

    def __iter__(self) -> Iterator[BaseTool]:
        return iter(self.tools)

    def __len__(self) -> int:
        return len(self.tools)


def resolve_state_tool_set(
    scene_tracker: "SceneTracker | None",
    status_manager: "StatusManager | None",
) -> StateToolSet:
    """Resolve the exact state capability set from the turn-local runtimes."""
    tools: list[BaseTool] = []
    if scene_tracker is not None:
        tools.extend(scene_tracker.get_tools())
    if status_manager is not None:
        tools.extend(StatusTableToolProvider(status_manager).get_tools())
    return StateToolSet.from_tools(tools)
