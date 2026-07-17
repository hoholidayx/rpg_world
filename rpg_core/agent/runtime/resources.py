"""Typed session-scoped resources owned by the Agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, cast

if TYPE_CHECKING:
    from rpg_core.character import CharacterManager
    from rpg_core.context import RPGContextBuilder
    from rpg_core.lorebook import LorebookManager
    from rpg_core.scene import SceneTracker
    from rpg_core.status.manager import StatusManager
    from rp_memory.memory_manager import MemoryManager


@dataclass(frozen=True, slots=True)
class AgentContextResources:
    """Immutable references to one session's context collaborators.

    The referenced managers remain mutable where their own APIs require it;
    freezing this carrier prevents partially replacing a runtime resource set.
    """

    builder: "RPGContextBuilder"
    character_manager: "CharacterManager | None"
    lorebook_manager: "LorebookManager | None"
    status_manager: "StatusManager | None"
    scene_tracker: "SceneTracker | None"
    memory_manager: "MemoryManager | None"

    async def close(self) -> None:
        """Release every session-scoped file watcher and storage handle."""

        try:
            if self.memory_manager is not None:
                await self.memory_manager.close()
        finally:
            self.builder.close()

    @classmethod
    def from_factory_result(
        cls,
        result: Mapping[str, object],
    ) -> "AgentContextResources":
        builder = result.get("builder")
        if builder is None:
            raise RuntimeError("RPG context factory did not return a builder")
        return cls(
            builder=cast("RPGContextBuilder", builder),
            character_manager=cast("CharacterManager | None", result.get("character_mgr")),
            lorebook_manager=cast("LorebookManager | None", result.get("lorebook_mgr")),
            status_manager=cast("StatusManager | None", result.get("status_mgr")),
            scene_tracker=cast("SceneTracker | None", result.get("scene_tracker")),
            memory_manager=cast("MemoryManager | None", result.get("memory_manager")),
        )


def build_agent_context_resources(
    *,
    world_name: str,
    session_id: str,
) -> AgentContextResources:
    """Build a complete resource set without leaking the factory mapping."""
    from rpg_core.context.factory import build_rpg_context

    return AgentContextResources.from_factory_result(
        build_rpg_context(world_name=world_name, session_id=session_id)
    )
