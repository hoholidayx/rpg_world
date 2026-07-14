"""Canonical provider-visible order for structured RPG context layers."""

from __future__ import annotations

from dataclasses import dataclass

from rpg_core.context.rpg_context import LayerType, Role


@dataclass(frozen=True)
class ContextLayerPlacement:
    """One structured layer's position and provider role."""

    type: str
    role: Role | None


CONTEXT_LAYER_ORDER: tuple[ContextLayerPlacement, ...] = (
    ContextLayerPlacement(LayerType.FIXED, Role.SYSTEM),
    ContextLayerPlacement(LayerType.PERSISTENT_MEMORY, Role.SYSTEM),
    ContextLayerPlacement(LayerType.SUMMARY, Role.SYSTEM),
    ContextLayerPlacement(LayerType.HOT_HISTORY, None),
    ContextLayerPlacement(LayerType.STORY_MEMORY, Role.SYSTEM),
    ContextLayerPlacement(LayerType.STATUS_TABLES, Role.SYSTEM),
    ContextLayerPlacement(LayerType.RECALLED_MEMORY, Role.SYSTEM),
    ContextLayerPlacement(LayerType.RP_MODULES, Role.SYSTEM),
    ContextLayerPlacement(LayerType.USER_MESSAGE, Role.USER),
)
"""Single source of truth shared by the renderer and diagnostics."""
