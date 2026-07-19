"""Deterministic candidate selection for the two plot scheduling lanes."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable

from commons.scene_time import SceneTime
from rpg_data import models as data_models
from rpg_core.rp_modules.plot_scheduler.models import (
    PlotScheduleCandidate,
    PlotScheduleSnapshot,
)


class PlotScheduleSelector:
    """Select at most one outline node and one pool event for a turn."""

    def select(
        self,
        snapshot: PlotScheduleSnapshot,
        *,
        scene_time: SceneTime,
        current_turn_id: int,
        completed_ic_gm_turn_ids: Iterable[int],
    ) -> tuple[PlotScheduleCandidate, ...]:
        if not snapshot.enabled:
            return ()
        completed_turn_ids = frozenset(
            int(turn_id)
            for turn_id in completed_ic_gm_turn_ids
            if 0 < int(turn_id) < int(current_turn_id)
        )
        event_by_id = {event.id: event for event in snapshot.story.events}
        selected: list[PlotScheduleCandidate] = []
        outline = self._select_outline(
            snapshot,
            event_by_id=event_by_id,
            scene_time=scene_time,
            current_turn_id=current_turn_id,
            completed_turn_ids=completed_turn_ids,
        )
        if outline is not None:
            selected.append(outline)
        pool = self._select_pool(
            snapshot,
            scene_time=scene_time,
            current_turn_id=current_turn_id,
            completed_turn_ids=completed_turn_ids,
            excluded_event_ids=(
                frozenset({outline.event.id})
                if outline is not None
                else frozenset()
            ),
        )
        if pool is not None:
            selected.append(pool)
        return tuple(selected)

    def _select_outline(
        self,
        snapshot: PlotScheduleSnapshot,
        *,
        event_by_id: dict[int, data_models.StoryPlotEvent],
        scene_time: SceneTime,
        current_turn_id: int,
        completed_turn_ids: frozenset[int],
    ) -> PlotScheduleCandidate | None:
        candidates: list[PlotScheduleCandidate] = []
        triggered_node_ids = {
            decision.source_id
            for decision in snapshot.decisions
            if decision.source_kind == data_models.PLOT_SOURCE_OUTLINE
            and decision.decision_status == data_models.PLOT_DECISION_TRIGGERED
        }
        disabled = snapshot.overrides.disabled_outline_node_ids
        for outline in snapshot.story.outlines:
            if not outline.enabled:
                continue
            head = next(
                (
                    node
                    for node in sorted(
                        outline.nodes,
                        key=lambda item: (item.position, item.id),
                    )
                    if node.enabled
                    and node.id not in disabled
                    and node.id not in triggered_node_ids
                ),
                None,
            )
            if head is None or head.scheduled_time > scene_time:
                continue
            event = event_by_id.get(head.event_id)
            if event is None:
                continue
            if not self._retry_ready(
                snapshot,
                source_kind=data_models.PLOT_SOURCE_OUTLINE,
                source_id=head.id,
                current_turn_id=current_turn_id,
                completed_turn_ids=completed_turn_ids,
            ):
                continue
            candidates.append(
                PlotScheduleCandidate(
                    source_kind=data_models.PLOT_SOURCE_OUTLINE,
                    source_id=head.id,
                    event=event,
                    container_id=outline.id,
                    container_name=outline.name,
                    dispatch_mode=head.dispatch_mode,
                    scheduled_time=head.scheduled_time,
                    priority=outline.priority,
                )
            )
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                item.scheduled_time.ordinal_minutes
                if item.scheduled_time is not None
                else 0,
                -item.priority,
                item.container_id,
                item.source_id,
            ),
        )

    def _select_pool(
        self,
        snapshot: PlotScheduleSnapshot,
        *,
        scene_time: SceneTime,
        current_turn_id: int,
        completed_turn_ids: frozenset[int],
        excluded_event_ids: frozenset[int],
    ) -> PlotScheduleCandidate | None:
        events_by_pool: dict[int, list[data_models.StoryPlotEvent]] = {}
        for event in snapshot.story.events:
            if event.enabled and event.id not in snapshot.overrides.disabled_event_ids:
                events_by_pool.setdefault(event.pool_id, []).append(event)

        for pool in sorted(
            snapshot.story.pools,
            key=lambda item: (-item.priority, item.id),
        ):
            if not pool.enabled:
                continue
            events = sorted(
                events_by_pool.get(pool.id, ()),
                key=lambda item: (item.position, item.id),
            )
            event = self._select_pool_event(
                snapshot,
                pool=pool,
                events=events,
                scene_time=scene_time,
                current_turn_id=current_turn_id,
                completed_turn_ids=completed_turn_ids,
                excluded_event_ids=excluded_event_ids,
            )
            if event is not None:
                return PlotScheduleCandidate(
                    source_kind=data_models.PLOT_SOURCE_POOL,
                    source_id=event.id,
                    event=event,
                    container_id=pool.id,
                    container_name=pool.name,
                    dispatch_mode=event.dispatch_mode,
                    scheduled_time=event.scheduled_time,
                    priority=pool.priority,
                )
        return None

    def _select_pool_event(
        self,
        snapshot: PlotScheduleSnapshot,
        *,
        pool: data_models.StoryPlotEventPool,
        events: list[data_models.StoryPlotEvent],
        scene_time: SceneTime,
        current_turn_id: int,
        completed_turn_ids: frozenset[int],
        excluded_event_ids: frozenset[int],
    ) -> data_models.StoryPlotEvent | None:
        if not events:
            return None
        current_event_ids = frozenset(event.id for event in events)
        pool_lane_decisions = [
            decision
            for decision in snapshot.decisions
            if decision.source_kind == data_models.PLOT_SOURCE_POOL
        ]
        triggered_by_event: dict[int, list[data_models.SessionPlotScheduleDecision]] = {}
        for decision in pool_lane_decisions:
            if decision.decision_status == data_models.PLOT_DECISION_TRIGGERED:
                triggered_by_event.setdefault(decision.event_id, []).append(decision)

        if pool.selection_mode == data_models.PLOT_POOL_SEQUENTIAL:
            for event in events:
                if event.id in triggered_by_event:
                    continue
                return event if self._pool_event_eligible(
                    snapshot,
                    event=event,
                    scene_time=scene_time,
                    current_turn_id=current_turn_id,
                    completed_turn_ids=completed_turn_ids,
                    triggered=(),
                    excluded_event_ids=excluded_event_ids,
                ) else None

            repeatable = [event for event in events if event.allow_repeat]
            if not repeatable:
                return None
            last_triggered = max(
                (
                    decision
                    for event_id, decisions in triggered_by_event.items()
                    if event_id in current_event_ids
                    for decision in decisions
                ),
                key=lambda item: (item.turn_id, item.id),
            )
            last_index = next(
                (
                    index
                    for index, event in enumerate(repeatable)
                    if event.id == last_triggered.event_id
                ),
                -1,
            )
            target = repeatable[(last_index + 1) % len(repeatable)]
            return target if self._pool_event_eligible(
                snapshot,
                event=target,
                scene_time=scene_time,
                current_turn_id=current_turn_id,
                completed_turn_ids=completed_turn_ids,
                triggered=tuple(triggered_by_event.get(target.id, ())),
                excluded_event_ids=excluded_event_ids,
            ) else None

        eligible = [
            event
            for event in events
            if self._pool_event_eligible(
                snapshot,
                event=event,
                scene_time=scene_time,
                current_turn_id=current_turn_id,
                completed_turn_ids=completed_turn_ids,
                triggered=tuple(triggered_by_event.get(event.id, ())),
                excluded_event_ids=excluded_event_ids,
            )
        ]
        if not eligible:
            return None
        seed = hashlib.sha256(
            f"{snapshot.session_id}:{current_turn_id}:{pool.id}".encode("utf-8")
        ).digest()
        return random.Random(seed).choice(eligible)

    def _pool_event_eligible(
        self,
        snapshot: PlotScheduleSnapshot,
        *,
        event: data_models.StoryPlotEvent,
        scene_time: SceneTime,
        current_turn_id: int,
        completed_turn_ids: frozenset[int],
        triggered: tuple[data_models.SessionPlotScheduleDecision, ...],
        excluded_event_ids: frozenset[int],
    ) -> bool:
        if event.id in excluded_event_ids:
            return False
        if not self._retry_ready(
            snapshot,
            source_kind=data_models.PLOT_SOURCE_POOL,
            source_id=event.id,
            current_turn_id=current_turn_id,
            completed_turn_ids=completed_turn_ids,
        ):
            return False
        if not triggered:
            return event.scheduled_time is None or event.scheduled_time <= scene_time
        if not event.allow_repeat:
            return False
        latest = max(triggered, key=lambda item: (item.turn_id, item.id))
        return (
            scene_time.ordinal_minutes - latest.scene_time_ordinal
            >= event.repeat_cooldown_minutes
        )

    @staticmethod
    def _retry_ready(
        snapshot: PlotScheduleSnapshot,
        *,
        source_kind: str,
        source_id: int,
        current_turn_id: int,
        completed_turn_ids: frozenset[int],
    ) -> bool:
        latest = max(
            (
                decision
                for decision in snapshot.decisions
                if decision.source_kind == source_kind
                and decision.source_id == source_id
            ),
            key=lambda item: (item.turn_id, item.id),
            default=None,
        )
        if latest is None or latest.decision_status == data_models.PLOT_DECISION_TRIGGERED:
            return True
        intervening = sum(
            latest.turn_id < turn_id < current_turn_id
            for turn_id in completed_turn_ids
        )
        return intervening >= snapshot.soft_retry_intervening_turns
