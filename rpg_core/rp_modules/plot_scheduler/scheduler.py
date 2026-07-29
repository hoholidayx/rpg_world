"""Deterministic candidate selection for the two plot scheduling lanes."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from commons.scene_time import SceneTime
from rpg_data import models as data_models
from rpg_core.rp_modules.plot_scheduler.diagnostics import (
    evaluate_pool_cooldowns,
    outline_bound_event_ids,
)
from rpg_core.rp_modules.plot_scheduler.models import (
    PlotScheduleCandidate,
    PlotScheduleCandidateBatch,
    PlotScheduleSnapshot,
)

_ItemT = TypeVar("_ItemT")


@dataclass(frozen=True)
class _PoolOption:
    pool: data_models.StoryPlotEventPool
    events: tuple[data_models.StoryPlotEvent, ...]


class PlotScheduleSelector:
    """Select at most one outline node and one pool event for a turn."""

    def select(
        self,
        snapshot: PlotScheduleSnapshot,
        *,
        scene_time: SceneTime,
        current_turn_id: int,
        completed_world_turn_ids: Iterable[int],
    ) -> tuple[PlotScheduleCandidate | PlotScheduleCandidateBatch, ...]:
        if not snapshot.enabled:
            return ()
        completed_turn_ids = frozenset(
            int(turn_id)
            for turn_id in completed_world_turn_ids
            if 0 < int(turn_id) < int(current_turn_id)
        )
        event_by_id = {event.id: event for event in snapshot.story.events}
        selected: list[PlotScheduleCandidate | PlotScheduleCandidateBatch] = []
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
                    and not self._event_expired(
                        event_by_id.get(node.event_id),
                        scene_time,
                    )
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
                    container_priority=outline.priority,
                    event_selection_weight=event.selection_weight,
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
                -(item.container_priority or 0),
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
    ) -> PlotScheduleCandidate | PlotScheduleCandidateBatch | None:
        outline_bound = outline_bound_event_ids(snapshot.story)
        events_by_pool: dict[int, list[data_models.StoryPlotEvent]] = {}
        for event in snapshot.story.events:
            if (
                event.enabled
                and event.id not in snapshot.overrides.disabled_event_ids
                and event.id not in outline_bound
            ):
                events_by_pool.setdefault(event.pool_id, []).append(event)

        cooldowns = {
            item.pool_id: item
            for item in evaluate_pool_cooldowns(
                snapshot.story.pools,
                snapshot.decisions,
                scene_time=scene_time,
            )
        }
        options: list[_PoolOption] = []
        for pool in sorted(snapshot.story.pools, key=lambda item: item.id):
            if not pool.enabled:
                continue
            cooldown = cooldowns[pool.id]
            if cooldown.blocks_automatic_selection:
                continue
            events = sorted(
                events_by_pool.get(pool.id, ()),
                key=(
                    (lambda item: (item.position, item.id))
                    if pool.selection_mode == data_models.PLOT_POOL_SEQUENTIAL
                    else (lambda item: item.id)
                ),
            )
            eligible = self._eligible_pool_events(
                snapshot,
                pool=pool,
                events=events,
                scene_time=scene_time,
                current_turn_id=current_turn_id,
                completed_turn_ids=completed_turn_ids,
                excluded_event_ids=excluded_event_ids,
            )
            if eligible:
                options.append(_PoolOption(pool=pool, events=eligible))
        if not options:
            return None

        selected = _stable_weighted_choice(
            options,
            [option.pool.selection_weight for option in options],
            seed=f"{snapshot.session_id}:{current_turn_id}:plot-pool-lane",
        )
        pool = selected.pool
        if pool.selection_mode == data_models.PLOT_POOL_SEQUENTIAL:
            return self._pool_candidate(pool, selected.events[0])

        primary_event = _stable_weighted_choice(
            selected.events,
            [event.selection_weight for event in selected.events],
            seed=(
                f"{snapshot.session_id}:{current_turn_id}:"
                f"plot-pool:{pool.id}:primary"
            ),
        )
        primary = self._pool_candidate(pool, primary_event)
        if primary.dispatch_mode == data_models.PLOT_DISPATCH_FORCED:
            return primary

        additional_events = _stable_weighted_sample_without_replacement(
            tuple(
                event
                for event in selected.events
                if event.id != primary_event.id
                and event.dispatch_mode == data_models.PLOT_DISPATCH_SOFT
            ),
            count=max(0, pool.candidate_batch_size - 1),
            seed=(
                f"{snapshot.session_id}:{current_turn_id}:"
                f"plot-pool:{pool.id}:soft-batch"
            ),
        )
        candidates = (
            primary,
            *(
                self._pool_candidate(pool, event)
                for event in additional_events
            ),
        )
        return PlotScheduleCandidateBatch(
            primary=primary,
            candidates=tuple(candidates),
            configured_size=pool.candidate_batch_size,
        )

    @staticmethod
    def _pool_candidate(
        pool: data_models.StoryPlotEventPool,
        event: data_models.StoryPlotEvent,
    ) -> PlotScheduleCandidate:
        return PlotScheduleCandidate(
            source_kind=data_models.PLOT_SOURCE_POOL,
            source_id=event.id,
            event=event,
            container_id=pool.id,
            container_name=pool.name,
            dispatch_mode=event.dispatch_mode,
            scheduled_time=event.scheduled_time,
            container_selection_weight=pool.selection_weight,
            event_selection_weight=event.selection_weight,
            pool_selection_mode=pool.selection_mode,
        )

    def _eligible_pool_events(
        self,
        snapshot: PlotScheduleSnapshot,
        *,
        pool: data_models.StoryPlotEventPool,
        events: list[data_models.StoryPlotEvent],
        scene_time: SceneTime,
        current_turn_id: int,
        completed_turn_ids: frozenset[int],
        excluded_event_ids: frozenset[int],
    ) -> tuple[data_models.StoryPlotEvent, ...]:
        if not events:
            return ()
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
                if self._event_expired(event, scene_time):
                    continue
                return (
                    (event,)
                    if self._pool_event_eligible(
                        snapshot,
                        event=event,
                        scene_time=scene_time,
                        current_turn_id=current_turn_id,
                        completed_turn_ids=completed_turn_ids,
                        triggered=(),
                        excluded_event_ids=excluded_event_ids,
                    )
                    else ()
                )

            repeatable = [event for event in events if event.allow_repeat]
            if not repeatable:
                return ()
            triggered = tuple(
                decision
                for event_id, decisions in triggered_by_event.items()
                if event_id in current_event_ids
                for decision in decisions
            )
            if not triggered:
                return ()
            last_triggered = max(triggered, key=lambda item: (item.turn_id, item.id))
            last_index = next(
                (
                    index
                    for index, event in enumerate(repeatable)
                    if event.id == last_triggered.event_id
                ),
                -1,
            )
            for offset in range(1, len(repeatable) + 1):
                target = repeatable[(last_index + offset) % len(repeatable)]
                if self._event_expired(target, scene_time):
                    continue
                return (
                    (target,)
                    if self._pool_event_eligible(
                        snapshot,
                        event=target,
                        scene_time=scene_time,
                        current_turn_id=current_turn_id,
                        completed_turn_ids=completed_turn_ids,
                        triggered=tuple(triggered_by_event.get(target.id, ())),
                        excluded_event_ids=excluded_event_ids,
                    )
                    else ()
                )
            return ()

        return tuple(
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
        )

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
        if self._event_expired(event, scene_time):
            return False
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
        if latest.scene_time_ordinal is None:
            # Explicit manual injection overrides automatic eligibility rules,
            # including any earlier SceneTime cooldown anchor.
            return True
        return (
            scene_time.ordinal_minutes - latest.scene_time_ordinal
            >= event.repeat_cooldown_minutes
        )

    @staticmethod
    def _event_expired(
        event: data_models.StoryPlotEvent | None,
        scene_time: SceneTime,
    ) -> bool:
        return (
            event is not None
            and event.deadline_time is not None
            and scene_time >= event.deadline_time
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


def _stable_weighted_choice(
    values: Sequence[_ItemT],
    weights: Sequence[int],
    *,
    seed: str,
) -> _ItemT:
    if not values or len(values) != len(weights):
        raise ValueError("weighted choice requires matching non-empty values and weights")
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).digest())
    return values[_weighted_index(weights, rng)]


def _stable_weighted_sample_without_replacement(
    values: Sequence[_ItemT],
    *,
    count: int,
    seed: str,
) -> tuple[_ItemT, ...]:
    remaining = list(values)
    weights = [int(value.selection_weight) for value in remaining]
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).digest())
    selected: list[_ItemT] = []
    for _ in range(min(max(0, count), len(remaining))):
        index = _weighted_index(weights, rng)
        selected.append(remaining.pop(index))
        weights.pop(index)
    return tuple(selected)


def _weighted_index(weights: Sequence[int], rng: random.Random) -> int:
    normalized = [int(weight) for weight in weights]
    if any(weight <= 0 for weight in normalized):
        raise ValueError("selection weights must be positive")
    ticket = rng.randrange(sum(normalized))
    cumulative = 0
    for index, weight in enumerate(normalized):
        cumulative += weight
        if ticket < cumulative:
            return index
    raise RuntimeError("weighted selection ticket exceeded total weight")
