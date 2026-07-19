"""Typed data contracts for Story plot scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from commons.scene_time import SceneTime

PLOT_DISPATCH_FORCED = "forced"
PLOT_DISPATCH_SOFT = "soft"
PLOT_DISPATCH_MODES = frozenset({PLOT_DISPATCH_FORCED, PLOT_DISPATCH_SOFT})

PLOT_POOL_RANDOM = "random"
PLOT_POOL_SEQUENTIAL = "sequential"
PLOT_POOL_MODES = frozenset({PLOT_POOL_RANDOM, PLOT_POOL_SEQUENTIAL})

PLOT_SOURCE_OUTLINE = "outline"
PLOT_SOURCE_POOL = "pool"
PLOT_SOURCE_KINDS = frozenset({PLOT_SOURCE_OUTLINE, PLOT_SOURCE_POOL})

PLOT_DECISION_TRIGGERED = "triggered"
PLOT_DECISION_DEFERRED = "deferred"
PLOT_DECISION_ERROR = "error"
PLOT_DECISION_STATUSES = frozenset({
    PLOT_DECISION_TRIGGERED,
    PLOT_DECISION_DEFERRED,
    PLOT_DECISION_ERROR,
})
PLOT_DECISION_PAGE_SIZE_MAX = 200


@dataclass(frozen=True)
class StoryPlotEventPool:
    id: int
    story_id: int
    name: str
    description: str = ""
    selection_mode: str = PLOT_POOL_RANDOM
    priority: int = 0
    enabled: bool = True
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryPlotEvent:
    id: int
    story_id: int
    pool_id: int
    title: str
    directive: str
    description: str = ""
    suitability_hint: str = ""
    dispatch_mode: str = PLOT_DISPATCH_SOFT
    scheduled_time: SceneTime | None = None
    position: int = 0
    enabled: bool = True
    allow_repeat: bool = False
    repeat_cooldown_minutes: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryPlotOutlineNode:
    id: int
    story_id: int
    outline_id: int
    event_id: int
    scheduled_time: SceneTime
    dispatch_mode: str = PLOT_DISPATCH_SOFT
    position: int = 0
    enabled: bool = True
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryPlotOutline:
    id: int
    story_id: int
    name: str
    description: str = ""
    priority: int = 0
    enabled: bool = True
    nodes: tuple[StoryPlotOutlineNode, ...] = ()
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryPlotSchedule:
    story_id: int
    pools: tuple[StoryPlotEventPool, ...] = ()
    events: tuple[StoryPlotEvent, ...] = ()
    outlines: tuple[StoryPlotOutline, ...] = ()


@dataclass(frozen=True)
class SessionPlotOverrides:
    session_id: str
    disabled_event_ids: frozenset[int] = frozenset()
    disabled_outline_node_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class SessionPlotScheduleDecision:
    id: int
    session_id: str
    turn_id: int
    source_kind: str
    source_id: int
    event_id: int
    container_id: int
    decision_status: str
    dispatch_mode: str
    scene_time: SceneTime
    scene_time_ordinal: int
    event_snapshot: Mapping[str, object] = field(default_factory=dict)
    reason: str = ""
    error_code: str = ""
    error_message: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StagedPlotScheduleDecision:
    source_kind: str
    source_id: int
    event_id: int
    container_id: int
    decision_status: str
    dispatch_mode: str
    scene_time: SceneTime
    event_snapshot: Mapping[str, object]
    reason: str = ""
    error_code: str = ""
    error_message: str = ""
