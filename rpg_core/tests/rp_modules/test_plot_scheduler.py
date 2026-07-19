from __future__ import annotations

from commons.scene_time import SceneTime
from rpg_data import models
from rpg_core.rp_modules.plot_scheduler import PlotScheduleSelector, PlotScheduleSnapshot


def _event(
    event_id: int,
    pool_id: int,
    *,
    position: int = 0,
    scheduled_time: SceneTime | None = None,
    repeat: bool = False,
    cooldown: int = 0,
) -> models.StoryPlotEvent:
    return models.StoryPlotEvent(
        id=event_id,
        story_id=1,
        pool_id=pool_id,
        title=f"事件 {event_id}",
        directive=f"执行事件 {event_id}",
        position=position,
        scheduled_time=scheduled_time,
        allow_repeat=repeat,
        repeat_cooldown_minutes=cooldown,
    )


def _decision(
    decision_id: int,
    turn_id: int,
    source_kind: str,
    source_id: int,
    event_id: int,
    container_id: int,
    status: str,
    *,
    scene_time: SceneTime = SceneTime(1, 1, 1, 8),
) -> models.SessionPlotScheduleDecision:
    return models.SessionPlotScheduleDecision(
        id=decision_id,
        session_id="s1",
        turn_id=turn_id,
        source_kind=source_kind,
        source_id=source_id,
        event_id=event_id,
        container_id=container_id,
        decision_status=status,
        dispatch_mode=models.PLOT_DISPATCH_SOFT,
        scene_time=scene_time,
        scene_time_ordinal=scene_time.ordinal_minutes,
    )


def test_selector_can_emit_one_due_outline_and_one_pool_event() -> None:
    pool_event = _event(1, 10)
    outline_event = _event(2, 10)
    node = models.StoryPlotOutlineNode(
        id=50,
        story_id=1,
        outline_id=20,
        event_id=outline_event.id,
        scheduled_time=SceneTime(1, 1, 1, 9),
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "随机池"),),
            events=(pool_event, outline_event),
            outlines=(models.StoryPlotOutline(20, 1, "主线", nodes=(node,)),),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
    )

    selected = PlotScheduleSelector().select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=2,
        completed_ic_gm_turn_ids=(1,),
    )

    assert [item.source_kind for item in selected] == ["outline", "pool"]
    assert selected[0].source_id == node.id
    assert selected[0].event.id != selected[1].event.id


def test_sequential_pool_retries_deferred_head_only_after_intervening_turn() -> None:
    first = _event(1, 10, position=0)
    second = _event(2, 10, position=1)
    deferred = _decision(
        1, 3, models.PLOT_SOURCE_POOL, first.id, first.id, 10,
        models.PLOT_DECISION_DEFERRED,
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "顺序池", selection_mode="sequential"),),
            events=(first, second),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(deferred,),
        soft_retry_intervening_turns=1,
    )
    selector = PlotScheduleSelector()

    assert selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=4,
        completed_ic_gm_turn_ids=(1, 2, 3),
    ) == ()
    retried = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=5,
        completed_ic_gm_turn_ids=(1, 2, 3, 4),
    )
    assert len(retried) == 1
    assert retried[0].event.id == first.id


def test_repeat_event_uses_scene_time_cooldown_and_random_is_stable() -> None:
    first = _event(1, 10, repeat=True, cooldown=60)
    second = _event(2, 10)
    triggered = _decision(
        1, 2, models.PLOT_SOURCE_POOL, first.id, first.id, 10,
        models.PLOT_DECISION_TRIGGERED,
        scene_time=SceneTime(1, 1, 1, 10),
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "随机池"),),
            events=(first, second),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(triggered,),
    )
    selector = PlotScheduleSelector()

    before = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 10, 30),
        current_turn_id=4,
        completed_ic_gm_turn_ids=(1, 2, 3),
    )
    assert before[0].event.id == second.id
    after_a = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 11),
        current_turn_id=5,
        completed_ic_gm_turn_ids=(1, 2, 3, 4),
    )
    after_b = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 11),
        current_turn_id=5,
        completed_ic_gm_turn_ids=(1, 2, 3, 4),
    )
    assert after_a == after_b


def test_non_repeat_event_keeps_pool_lane_trigger_after_moving_pools() -> None:
    moved = _event(1, 20)
    triggered_in_old_pool = _decision(
        1,
        2,
        models.PLOT_SOURCE_POOL,
        moved.id,
        moved.id,
        10,
        models.PLOT_DECISION_TRIGGERED,
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(20, 1, "新事件池"),),
            events=(moved,),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(triggered_in_old_pool,),
    )

    selected = PlotScheduleSelector().select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=4,
        completed_ic_gm_turn_ids=(1, 2, 3),
    )

    assert selected == ()
