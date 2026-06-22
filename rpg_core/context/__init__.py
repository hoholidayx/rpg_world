"""RPG World context — layered context builder and factory."""

from rpg_world.rpg_core.context.builder import RPGContextBuilder
from rpg_world.rpg_core.context.config import RPGContextConfig
from rpg_world.rpg_core.context.factory import build_rpg_context
from rpg_world.rpg_core.context.fixed_layer import FixedLayerComposer, FixedLayerSection
from rpg_world.rpg_core.context.inspector import ContextInspector, LayerInfo
from rpg_world.rpg_core.context.renderer import ContextRenderer
from rpg_world.rpg_core.context.rpg_context import (
    FixedLayerData,
    HotHistoryLayer,
    LayerType,
    PersistentMemoryLayer,
    RecalledMemoryLayer,
    RPGContext,
    RPModuleRuntimeSection,
    RPModulesLayer,
    StatusTablesLayer,
    StoryMemoryLayer,
    SummaryLayer,
    UserMessageLayer,
)

__all__ = [
    "FixedLayerComposer",
    "FixedLayerData",
    "FixedLayerSection",
    "HotHistoryLayer",
    "ContextInspector",
    "ContextRenderer",
    "LayerType",
    "LayerInfo",
    "PersistentMemoryLayer",
    "RecalledMemoryLayer",
    "RPGContext",
    "RPGContextBuilder",
    "RPGContextConfig",
    "RPModuleRuntimeSection",
    "RPModulesLayer",
    "StatusTablesLayer",
    "StoryMemoryLayer",
    "SummaryLayer",
    "UserMessageLayer",
    "build_rpg_context",
]
