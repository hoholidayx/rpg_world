from __future__ import annotations

from types import SimpleNamespace

from commons.scene_time import SceneTime
from rpg_data import models
from rpg_core.context import RPModuleRuntimePlacement
from rpg_core.context.fixed_layer.rendering import render_fixed_layer_sections
from rpg_core.rp_modules.constants import (
    RP_MODULE_PLOT_SCHEDULER_TURN_SECTION_ID,
)
from rpg_core.rp_modules.models import ModuleContextRequest
from rpg_core.rp_modules.plot_scheduler import (
    PlotScheduleInjection,
    PlotScheduleSelector,
    PlotScheduleSnapshot,
    PlotSchedulerModule,
)
from rpg_core.settings import PlotSchedulerModuleSettings
from rpg_core.utils.tokenizer import TiktokenTokenCounter


def _event(
    event_id: int,
    pool_id: int,
    *,
    position: int = 0,
    scheduled_time: SceneTime | None = None,
    deadline_time: SceneTime | None = None,
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
        deadline_time=deadline_time,
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


def _injection(
    *,
    title: str,
    directive: str,
    source_kind: str,
    source_id: int,
    event_id: int,
    container_id: int,
    container_name: str,
) -> PlotScheduleInjection:
    return PlotScheduleInjection(
        source_kind=source_kind,
        source_id=source_id,
        event_id=event_id,
        container_id=container_id,
        container_name=container_name,
        event_title=title,
        directive=directive,
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
        scene_time=SceneTime(1, 1, 1, 10),
        reason="内部适宜性理由",
    )


def test_plot_fixed_contract_is_stable_and_defines_suffix_precedence() -> None:
    module = PlotSchedulerModule(session_id="s1")
    before = module.get_fixed_sections()
    module.bind_turn(
        SimpleNamespace(
            plot_schedule_injections=[
                _injection(
                    title="雨夜来信",
                    directive="让信使进入门厅。",
                    source_kind=models.PLOT_SOURCE_POOL,
                    source_id=1,
                    event_id=1,
                    container_id=10,
                    container_name="秘密事件池",
                )
            ]
        )
    )
    after = module.get_fixed_sections()

    assert render_fixed_layer_sections(before).encode() == (
        render_fixed_layer_sections(after).encode()
    )
    content = before[0].content
    assert f"[{RP_MODULE_PLOT_SCHEDULER_TURN_SECTION_ID}]" in content
    assert "优先于本轮玩家输入" in content
    assert "Narrative Outcome 最终裁定" in content
    assert "实际提供的工具边界" in content
    assert "除 GM 模式明确托管外" in content
    assert "台词、动作、选择" in content
    assert "按给定顺序兼容地落实全部指令" in content


def test_plot_runtime_section_is_concise_ordered_user_suffix() -> None:
    module = PlotSchedulerModule(session_id="s1")
    module.bind_turn(
        SimpleNamespace(
            plot_schedule_injections=[
                _injection(
                    title="雨夜来信",
                    directive="让信使进入门厅。",
                    source_kind=models.PLOT_SOURCE_OUTLINE,
                    source_id=51,
                    event_id=101,
                    container_id=20,
                    container_name="第一章",
                ),
                _injection(
                    title="远方钟声",
                    directive="三声钟响打断交谈。",
                    source_kind=models.PLOT_SOURCE_POOL,
                    source_id=102,
                    event_id=102,
                    container_id=30,
                    container_name="城镇事件池",
                ),
            ]
        )
    )

    sections = module.get_runtime_sections(
        ModuleContextRequest(
            session_id="s1",
            include_staged_turn=True,
        )
    )

    assert len(sections) == 1
    section = sections[0]
    assert section.id == RP_MODULE_PLOT_SCHEDULER_TURN_SECTION_ID
    assert section.placement is RPModuleRuntimePlacement.USER_SUFFIX
    assert section.content == (
        "1. 事件标题：雨夜来信\n"
        "   剧情指令：让信使进入门厅。\n"
        "2. 事件标题：远方钟声\n"
        "   剧情指令：三声钟响打断交谈。"
    )
    for internal_value in (
        "outline",
        "pool",
        "第一章",
        "城镇事件池",
        "forced",
        "第 1 年",
        "内部适宜性理由",
    ):
        assert internal_value not in section.content


def test_plot_runtime_suffix_is_absent_when_not_applicable() -> None:
    injection = _injection(
        title="雨夜来信",
        directive="让信使进入门厅。",
        source_kind=models.PLOT_SOURCE_POOL,
        source_id=1,
        event_id=1,
        container_id=10,
        container_name="秘密事件池",
    )
    module = PlotSchedulerModule(session_id="s1")
    module.bind_turn(SimpleNamespace(plot_schedule_injections=[injection]))

    assert module.get_runtime_sections(
        ModuleContextRequest(session_id="s1", include_staged_turn=False)
    ) == []
    assert module.get_runtime_sections(
        ModuleContextRequest(
            session_id="s1",
            include_staged_turn=True,
            message_mode="ooc",
        )
    ) == []

    empty = PlotSchedulerModule(session_id="s1")
    empty.bind_turn(SimpleNamespace(plot_schedule_injections=[]))
    assert empty.get_runtime_sections(
        ModuleContextRequest(session_id="s1", include_staged_turn=True)
    ) == []

    disabled = PlotSchedulerModule(
        session_id="s1",
        settings=PlotSchedulerModuleSettings(enabled=False),
    )
    disabled.bind_turn(SimpleNamespace(plot_schedule_injections=[injection]))
    assert disabled.get_runtime_sections(
        ModuleContextRequest(session_id="s1", include_staged_turn=True)
    ) == []


def test_context_gate_reserve_covers_two_concise_plot_suffix_items() -> None:
    events = (
        _event(1, 10),
        _event(2, 10),
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "事件池"),),
            events=events,
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
    )
    module = PlotSchedulerModule(session_id="s1")
    module.bind_turn(
        SimpleNamespace(
            plot_schedule_injections=[
                _injection(
                    title=event.title,
                    directive=event.directive,
                    source_kind=models.PLOT_SOURCE_POOL,
                    source_id=event.id,
                    event_id=event.id,
                    container_id=10,
                    container_name="事件池",
                )
                for event in events
            ]
        )
    )
    section = module.get_runtime_sections(
        ModuleContextRequest(session_id="s1", include_staged_turn=True)
    )[0]
    rendered_suffix = (
        f"[{section.id}]\n{section.content}\n[/{section.id}]"
    )
    counter = TiktokenTokenCounter()

    assert counter.count(snapshot.context_gate_reserve_text) >= counter.count(
        rendered_suffix
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
        completed_world_turn_ids=(1,),
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
        completed_world_turn_ids=(1, 2, 3),
    ) == ()
    retried = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=5,
        completed_world_turn_ids=(1, 2, 3, 4),
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
        completed_world_turn_ids=(1, 2, 3),
    )
    assert before[0].event.id == second.id
    after_a = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 11),
        current_turn_id=5,
        completed_world_turn_ids=(1, 2, 3, 4),
    )
    after_b = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 11),
        current_turn_id=5,
        completed_world_turn_ids=(1, 2, 3, 4),
    )
    assert after_a == after_b


def test_manual_trigger_without_scene_time_overrides_prior_cooldown() -> None:
    event = _event(1, 10, repeat=True, cooldown=60)
    anchored = _decision(
        1,
        2,
        models.PLOT_SOURCE_POOL,
        event.id,
        event.id,
        10,
        models.PLOT_DECISION_TRIGGERED,
        scene_time=SceneTime(1, 1, 1, 8),
    )
    manual = models.SessionPlotScheduleDecision(
        id=2,
        session_id="s1",
        turn_id=3,
        source_kind=models.PLOT_SOURCE_POOL,
        source_id=event.id,
        event_id=event.id,
        container_id=10,
        decision_status=models.PLOT_DECISION_TRIGGERED,
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
        selection_origin=models.PLOT_SELECTION_ORIGIN_MANUAL,
        scene_time=None,
        scene_time_ordinal=None,
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "冷却池"),),
            events=(event,),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(anchored, manual),
    )

    selected = PlotScheduleSelector().select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 8, 10),
        current_turn_id=4,
        completed_world_turn_ids=(1, 2, 3),
    )

    assert selected[0].event.id == event.id


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
        completed_world_turn_ids=(1, 2, 3),
    )

    assert selected == ()


def test_pool_event_window_includes_start_and_excludes_deadline_across_month() -> None:
    start = SceneTime(1, 1, 31, 23, 30)
    deadline = SceneTime(1, 2, 1, 0)
    event = _event(1, 10, scheduled_time=start, deadline_time=deadline)
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "窗口池"),),
            events=(event,),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
    )
    selector = PlotScheduleSelector()

    selected = selector.select(
        snapshot,
        scene_time=start,
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    )
    assert [item.event.id for item in selected] == [event.id]
    assert selector.select(
        snapshot,
        scene_time=deadline,
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    ) == ()


def test_deadline_without_start_expires_an_immediately_eligible_event() -> None:
    deadline = SceneTime(1, 1, 1, 10)
    event = _event(1, 10, deadline_time=deadline)
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "窗口池"),),
            events=(event,),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
    )
    selector = PlotScheduleSelector()

    assert [item.event.id for item in selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 9, 59),
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    )] == [event.id]
    assert selector.select(
        snapshot,
        scene_time=deadline,
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    ) == ()


def test_sequential_pool_skips_expired_head_but_keeps_future_head_blocking() -> None:
    expired = _event(1, 10, position=0, deadline_time=SceneTime(1, 1, 1, 10))
    following = _event(2, 10, position=1)
    selector = PlotScheduleSelector()
    expired_snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "顺序池", selection_mode="sequential"),),
            events=(expired, following),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
    )

    selected = selector.select(
        expired_snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    )
    assert [item.event.id for item in selected] == [following.id]

    future = _event(3, 10, position=0, scheduled_time=SceneTime(1, 1, 1, 11))
    future_snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "顺序池", selection_mode="sequential"),),
            events=(future, following),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
    )
    assert selector.select(
        future_snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    ) == ()


def test_outline_skips_expired_shared_event_and_continues_next_node() -> None:
    deadline = SceneTime(1, 1, 1, 10)
    expired = _event(1, 10, deadline_time=deadline)
    following = _event(2, 10)
    first_outline = models.StoryPlotOutline(
        20,
        1,
        "主线 A",
        nodes=(
            models.StoryPlotOutlineNode(
                50, 1, 20, expired.id, SceneTime(1, 1, 1, 8), position=0
            ),
            models.StoryPlotOutlineNode(
                51, 1, 20, following.id, SceneTime(1, 1, 1, 9), position=1
            ),
        ),
    )
    second_outline = models.StoryPlotOutline(
        21,
        1,
        "主线 B",
        nodes=(
            models.StoryPlotOutlineNode(
                52, 1, 21, expired.id, SceneTime(1, 1, 1, 8)
            ),
        ),
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "禁用池", enabled=False),),
            events=(expired, following),
            outlines=(first_outline, second_outline),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
    )

    selected = PlotScheduleSelector().select(
        snapshot,
        scene_time=deadline,
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    )

    assert len(selected) == 1
    assert selected[0].source_kind == models.PLOT_SOURCE_OUTLINE
    assert selected[0].source_id == 51
    assert selected[0].event.id == following.id


def test_repeatable_event_stops_participating_at_deadline() -> None:
    deadline = SceneTime(1, 1, 1, 10)
    event = _event(
        1,
        10,
        repeat=True,
        cooldown=1,
        deadline_time=deadline,
    )
    triggered = _decision(
        1,
        1,
        models.PLOT_SOURCE_POOL,
        event.id,
        event.id,
        10,
        models.PLOT_DECISION_TRIGGERED,
        scene_time=SceneTime(1, 1, 1, 9),
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(10, 1, "重复池"),),
            events=(event,),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(triggered,),
    )

    assert PlotScheduleSelector().select(
        snapshot,
        scene_time=deadline,
        current_turn_id=3,
        completed_world_turn_ids=(1, 2),
    ) == ()
