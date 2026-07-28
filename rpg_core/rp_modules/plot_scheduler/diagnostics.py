"""Pure Plot Scheduler eligibility diagnostics shared by runtime surfaces."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from commons.scene_time import SceneTime
from rpg_data import models as data_models

PLOT_POOL_COOLDOWN_INACTIVE = "inactive"
PLOT_POOL_COOLDOWN_READY = "ready"
PLOT_POOL_COOLDOWN_ACTIVE = "cooling_down"
PLOT_POOL_COOLDOWN_SCENE_TIME_UNAVAILABLE = "scene_time_unavailable"
PLOT_POOL_COOLDOWN_STATUSES = frozenset({
    PLOT_POOL_COOLDOWN_INACTIVE,
    PLOT_POOL_COOLDOWN_READY,
    PLOT_POOL_COOLDOWN_ACTIVE,
    PLOT_POOL_COOLDOWN_SCENE_TIME_UNAVAILABLE,
})

PLOT_POOL_COOLDOWN_REASON_INACTIVE = "pool_cooldown_inactive"
PLOT_POOL_COOLDOWN_REASON_NO_ANCHOR = "pool_cooldown_no_anchor"
PLOT_POOL_COOLDOWN_REASON_READY = "pool_cooldown_ready"
PLOT_POOL_COOLDOWN_REASON_ACTIVE = "pool_cooldown_active"
PLOT_POOL_COOLDOWN_REASON_SCENE_TIME_UNAVAILABLE = "scene_time_unavailable"


@dataclass(frozen=True)
class PlotPoolCooldownDiagnostic:
    pool_id: int
    cooldown_minutes: int
    status: str
    blocks_automatic_selection: bool
    elapsed_minutes: int | None
    remaining_minutes: int | None
    reason_code: str
    reason: str
    anchor: data_models.SessionPlotScheduleDecision | None


@dataclass(frozen=True)
class PlotEventBindingDiagnostic:
    event_id: int
    outline_bound: bool
    outline_node_reference_count: int
    pool_lane_eligible_by_binding: bool


def evaluate_pool_cooldowns(
    pools: Iterable[data_models.StoryPlotEventPool],
    decisions: Iterable[data_models.SessionPlotScheduleDecision],
    *,
    scene_time: SceneTime | None,
) -> tuple[PlotPoolCooldownDiagnostic, ...]:
    anchors = _latest_pool_anchors(decisions)
    return tuple(
        _evaluate_pool_cooldown(
            pool,
            anchor=anchors.get(pool.id),
            scene_time=scene_time,
        )
        for pool in pools
    )


def evaluate_event_bindings(
    schedule: data_models.StoryPlotSchedule,
) -> tuple[PlotEventBindingDiagnostic, ...]:
    reference_counts: dict[int, int] = {}
    for outline in schedule.outlines:
        for node in outline.nodes:
            reference_counts[node.event_id] = (
                reference_counts.get(node.event_id, 0) + 1
            )
    return tuple(
        PlotEventBindingDiagnostic(
            event_id=event.id,
            outline_bound=reference_counts.get(event.id, 0) > 0,
            outline_node_reference_count=reference_counts.get(event.id, 0),
            pool_lane_eligible_by_binding=reference_counts.get(event.id, 0) == 0,
        )
        for event in schedule.events
    )


def outline_bound_event_ids(
    schedule: data_models.StoryPlotSchedule,
) -> frozenset[int]:
    return frozenset(
        node.event_id
        for outline in schedule.outlines
        for node in outline.nodes
    )


def _latest_pool_anchors(
    decisions: Iterable[data_models.SessionPlotScheduleDecision],
) -> dict[int, data_models.SessionPlotScheduleDecision]:
    anchors: dict[int, data_models.SessionPlotScheduleDecision] = {}
    for decision in decisions:
        if (
            decision.source_kind != data_models.PLOT_SOURCE_POOL
            or decision.selection_origin
            != data_models.PLOT_SELECTION_ORIGIN_SCHEDULER
            or decision.decision_status
            != data_models.PLOT_DECISION_TRIGGERED
        ):
            continue
        current = anchors.get(decision.container_id)
        if current is None or (decision.turn_id, decision.id) > (
            current.turn_id,
            current.id,
        ):
            anchors[decision.container_id] = decision
    return anchors


def _evaluate_pool_cooldown(
    pool: data_models.StoryPlotEventPool,
    *,
    anchor: data_models.SessionPlotScheduleDecision | None,
    scene_time: SceneTime | None,
) -> PlotPoolCooldownDiagnostic:
    cooldown_minutes = int(pool.cooldown_minutes)
    if cooldown_minutes <= 0:
        return PlotPoolCooldownDiagnostic(
            pool_id=pool.id,
            cooldown_minutes=0,
            status=PLOT_POOL_COOLDOWN_INACTIVE,
            blocks_automatic_selection=False,
            elapsed_minutes=None,
            remaining_minutes=0,
            reason_code=PLOT_POOL_COOLDOWN_REASON_INACTIVE,
            reason="池级冷却为 0，不阻断自动事件池候选。",
            anchor=anchor,
        )
    if anchor is None:
        return PlotPoolCooldownDiagnostic(
            pool_id=pool.id,
            cooldown_minutes=cooldown_minutes,
            status=PLOT_POOL_COOLDOWN_READY,
            blocks_automatic_selection=False,
            elapsed_minutes=None,
            remaining_minutes=0,
            reason_code=PLOT_POOL_COOLDOWN_REASON_NO_ANCHOR,
            reason="尚无自动事件池成功注入记录，池级冷却不阻断候选。",
            anchor=None,
        )
    if scene_time is None or anchor.scene_time_ordinal is None:
        return PlotPoolCooldownDiagnostic(
            pool_id=pool.id,
            cooldown_minutes=cooldown_minutes,
            status=PLOT_POOL_COOLDOWN_SCENE_TIME_UNAVAILABLE,
            blocks_automatic_selection=False,
            elapsed_minutes=None,
            remaining_minutes=None,
            reason_code=PLOT_POOL_COOLDOWN_REASON_SCENE_TIME_UNAVAILABLE,
            reason="当前 SceneTime 不可用，无法计算池级冷却。",
            anchor=anchor,
        )
    elapsed_minutes = (
        scene_time.ordinal_minutes - anchor.scene_time_ordinal
    )
    remaining_minutes = max(0, cooldown_minutes - elapsed_minutes)
    if remaining_minutes > 0:
        return PlotPoolCooldownDiagnostic(
            pool_id=pool.id,
            cooldown_minutes=cooldown_minutes,
            status=PLOT_POOL_COOLDOWN_ACTIVE,
            blocks_automatic_selection=True,
            elapsed_minutes=elapsed_minutes,
            remaining_minutes=remaining_minutes,
            reason_code=PLOT_POOL_COOLDOWN_REASON_ACTIVE,
            reason=(
                "距最近一次自动事件池成功注入仍需 "
                f"{remaining_minutes} 个 SceneTime 分钟，跳过整个事件池。"
            ),
            anchor=anchor,
        )
    return PlotPoolCooldownDiagnostic(
        pool_id=pool.id,
        cooldown_minutes=cooldown_minutes,
        status=PLOT_POOL_COOLDOWN_READY,
        blocks_automatic_selection=False,
        elapsed_minutes=elapsed_minutes,
        remaining_minutes=0,
        reason_code=PLOT_POOL_COOLDOWN_REASON_READY,
        reason="池级冷却已经结束，不再阻断自动事件池候选。",
        anchor=anchor,
    )


__all__ = [
    "PLOT_POOL_COOLDOWN_ACTIVE",
    "PLOT_POOL_COOLDOWN_INACTIVE",
    "PLOT_POOL_COOLDOWN_READY",
    "PLOT_POOL_COOLDOWN_SCENE_TIME_UNAVAILABLE",
    "PLOT_POOL_COOLDOWN_STATUSES",
    "PlotEventBindingDiagnostic",
    "PlotPoolCooldownDiagnostic",
    "evaluate_event_bindings",
    "evaluate_pool_cooldowns",
    "outline_bound_event_ids",
]
