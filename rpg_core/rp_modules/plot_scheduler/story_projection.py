"""Player-facing Plot Story projection with server-side spoiler masking."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol

from commons.scene_time import SceneTime
from rpg_data import models as data_models

PLOT_STORY_LINE_OUTLINE = data_models.PLOT_SOURCE_OUTLINE
PLOT_STORY_LINE_POOL = data_models.PLOT_SOURCE_POOL


@dataclass(frozen=True)
class PlotStoryEventDetail:
    event_id: int
    title: str
    description: str
    directive: str
    suitability_hint: str
    dispatch_mode: str
    scheduled_time: SceneTime | None
    deadline_time: SceneTime | None
    allow_repeat: bool
    repeat_cooldown_minutes: int
    event_enabled: bool


@dataclass(frozen=True)
class PlotStoryNode:
    slot_key: str
    position: int
    revealed: bool
    enabled: bool
    session_disabled: bool
    event_injected: bool
    event_injection_count: int
    last_event_injection_turn_id: int | None
    source_injected: bool
    source_injection_count: int
    last_source_injection_turn_id: int | None
    event_detail: PlotStoryEventDetail | None


@dataclass(frozen=True)
class PlotStoryLine:
    kind: str
    id: int
    name: str
    description: str
    enabled: bool
    nodes: tuple[PlotStoryNode, ...] = ()


@dataclass(frozen=True)
class SessionPlotStory:
    session_id: str
    spoiler_protection_enabled: bool
    outlines: tuple[PlotStoryLine, ...] = ()
    pools: tuple[PlotStoryLine, ...] = ()


class PlotStoryProjectionDataPort(Protocol):
    def get_session_schedule(
        self,
        session_id: str,
    ) -> tuple[
        data_models.StoryPlotSchedule,
        data_models.SessionPlotOverrides,
    ]: ...

    def summarize_session_decisions(
        self,
        session_id: str,
        *,
        decision_statuses: Collection[str],
    ) -> data_models.SessionPlotDecisionAggregates: ...


class PlotStoryProjectionService:
    """Project current Plot definitions through committed Session decisions."""

    def __init__(self, data: PlotStoryProjectionDataPort) -> None:
        self._data = data

    def project(
        self,
        session_id: str,
        *,
        reveal_spoilers: bool = False,
    ) -> SessionPlotStory:
        schedule, overrides = self._data.get_session_schedule(session_id)
        aggregates = self._data.summarize_session_decisions(
            session_id,
            decision_statuses=(data_models.PLOT_DECISION_TRIGGERED,),
        )
        event_stats = {item.event_id: item for item in aggregates.events}
        source_stats = {
            (item.source_kind, item.source_id): item
            for item in aggregates.sources
        }
        events_by_id = {event.id: event for event in schedule.events}

        outlines: list[PlotStoryLine] = []
        for outline in sorted(
            schedule.outlines,
            key=lambda item: (-item.priority, item.id),
        ):
            nodes: list[PlotStoryNode] = []
            ordered_nodes = sorted(
                outline.nodes,
                key=lambda item: (item.position, item.id),
            )
            for index, node in enumerate(ordered_nodes):
                event = events_by_id.get(node.event_id)
                if event is None:
                    raise ValueError(
                        f"plot outline node references missing event: {node.id}"
                    )
                nodes.append(
                    _project_node(
                        line_kind=PLOT_STORY_LINE_OUTLINE,
                        line_id=outline.id,
                        item_index=index,
                        source_id=node.id,
                        position=node.position,
                        source_enabled=node.enabled,
                        session_disabled=(
                            node.id in overrides.disabled_outline_node_ids
                        ),
                        event=event,
                        dispatch_mode=node.dispatch_mode,
                        scheduled_time=node.scheduled_time,
                        allow_repeat=False,
                        repeat_cooldown_minutes=0,
                        reveal_spoilers=reveal_spoilers,
                        event_stats=event_stats,
                        source_stats=source_stats,
                    )
                )
            outlines.append(
                PlotStoryLine(
                    kind=PLOT_STORY_LINE_OUTLINE,
                    id=outline.id,
                    name=outline.name,
                    description=outline.description,
                    enabled=outline.enabled,
                    nodes=tuple(nodes),
                )
            )

        events_by_pool: dict[int, list[data_models.StoryPlotEvent]] = {}
        for event in schedule.events:
            events_by_pool.setdefault(event.pool_id, []).append(event)
        pools: list[PlotStoryLine] = []
        for pool in sorted(schedule.pools, key=lambda item: item.id):
            nodes = [
                _project_node(
                    line_kind=PLOT_STORY_LINE_POOL,
                    line_id=pool.id,
                    item_index=index,
                    source_id=event.id,
                    position=event.position,
                    source_enabled=event.enabled,
                    session_disabled=(
                        event.id in overrides.disabled_event_ids
                    ),
                    event=event,
                    dispatch_mode=event.dispatch_mode,
                    scheduled_time=event.scheduled_time,
                    allow_repeat=event.allow_repeat,
                    repeat_cooldown_minutes=event.repeat_cooldown_minutes,
                    reveal_spoilers=reveal_spoilers,
                    event_stats=event_stats,
                    source_stats=source_stats,
                )
                for index, event in enumerate(
                    sorted(
                        events_by_pool.get(pool.id, ()),
                        key=lambda item: (item.position, item.id),
                    )
                )
            ]
            pools.append(
                PlotStoryLine(
                    kind=PLOT_STORY_LINE_POOL,
                    id=pool.id,
                    name=pool.name,
                    description=pool.description,
                    enabled=pool.enabled,
                    nodes=tuple(nodes),
                )
            )

        return SessionPlotStory(
            session_id=str(session_id),
            spoiler_protection_enabled=not reveal_spoilers,
            outlines=tuple(outlines),
            pools=tuple(pools),
        )


def _project_node(
    *,
    line_kind: str,
    line_id: int,
    item_index: int,
    source_id: int,
    position: int,
    source_enabled: bool,
    session_disabled: bool,
    event: data_models.StoryPlotEvent,
    dispatch_mode: str,
    scheduled_time: SceneTime | None,
    allow_repeat: bool,
    repeat_cooldown_minutes: int,
    reveal_spoilers: bool,
    event_stats: dict[int, data_models.SessionPlotEventDecisionAggregate],
    source_stats: dict[
        tuple[str, int],
        data_models.SessionPlotSourceDecisionAggregate,
    ],
) -> PlotStoryNode:
    event_summary = event_stats.get(event.id)
    source_summary = source_stats.get((line_kind, source_id))
    revealed = reveal_spoilers or item_index == 0 or event_summary is not None
    return PlotStoryNode(
        slot_key=f"{line_kind}:{line_id}:{item_index}",
        position=position,
        revealed=revealed,
        enabled=source_enabled,
        session_disabled=session_disabled,
        event_injected=event_summary is not None,
        event_injection_count=(
            event_summary.decision_count if event_summary is not None else 0
        ),
        last_event_injection_turn_id=(
            event_summary.latest_turn_id if event_summary is not None else None
        ),
        source_injected=source_summary is not None,
        source_injection_count=(
            source_summary.decision_count if source_summary is not None else 0
        ),
        last_source_injection_turn_id=(
            source_summary.latest_turn_id if source_summary is not None else None
        ),
        event_detail=(
            PlotStoryEventDetail(
                event_id=event.id,
                title=event.title,
                description=event.description,
                directive=event.directive,
                suitability_hint=event.suitability_hint,
                dispatch_mode=dispatch_mode,
                scheduled_time=scheduled_time,
                deadline_time=event.deadline_time,
                allow_repeat=allow_repeat,
                repeat_cooldown_minutes=repeat_cooldown_minutes,
                event_enabled=event.enabled,
            )
            if revealed
            else None
        ),
    )


__all__ = [
    "PLOT_STORY_LINE_OUTLINE",
    "PLOT_STORY_LINE_POOL",
    "PlotStoryEventDetail",
    "PlotStoryLine",
    "PlotStoryNode",
    "PlotStoryProjectionDataPort",
    "PlotStoryProjectionService",
    "SessionPlotStory",
]
