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
    PLOT_POOL_COOLDOWN_ACTIVE,
    PlotScheduleCandidateBatch,
    PlotScheduleInjection,
    PlotScheduleSelector,
    PlotScheduleSnapshot,
    PlotSchedulerModule,
    evaluate_pool_cooldowns,
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
    dispatch_mode: str = models.PLOT_DISPATCH_SOFT,
    selection_weight: int = 1,
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
        dispatch_mode=dispatch_mode,
        allow_repeat=repeat,
        repeat_cooldown_minutes=cooldown,
        selection_weight=selection_weight,
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
    scene_time: SceneTime | None = SceneTime(1, 1, 1, 8),
    selection_origin: str = models.PLOT_SELECTION_ORIGIN_SCHEDULER,
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
        selection_origin=selection_origin,
        scene_time=scene_time,
        scene_time_ordinal=(
            scene_time.ordinal_minutes if scene_time is not None else None
        ),
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
        "1 年",
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
        scene_opportunity=models.SessionPlotSceneOpportunity(
            session_id="s1",
            source_turn_id=1,
        ),
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


def test_pool_selection_is_stable_and_tracks_configured_weights() -> None:
    high_pool = models.StoryPlotEventPool(
        10,
        1,
        "高权重池",
        selection_weight=9,
    )
    low_pool = models.StoryPlotEventPool(
        20,
        1,
        "低权重池",
        selection_weight=1,
    )
    high_event = _event(
        1,
        high_pool.id,
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
    )
    low_event = _event(
        2,
        low_pool.id,
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
    )
    snapshots = (
        PlotScheduleSnapshot(
            session_id="weighted-pools",
            story_id=1,
            enabled=True,
            story=models.StoryPlotSchedule(
                story_id=1,
                pools=(high_pool, low_pool),
                events=(high_event, low_event),
            ),
            overrides=models.SessionPlotOverrides("weighted-pools"),
            decisions=(),
        ),
        PlotScheduleSnapshot(
            session_id="weighted-pools",
            story_id=1,
            enabled=True,
            story=models.StoryPlotSchedule(
                story_id=1,
                pools=(low_pool, high_pool),
                events=(low_event, high_event),
            ),
            overrides=models.SessionPlotOverrides("weighted-pools"),
            decisions=(),
        ),
    )
    selector = PlotScheduleSelector()
    selected_pool_ids: list[int] = []

    for turn_id in range(1, 1001):
        forward = selector.select(
            snapshots[0],
            scene_time=SceneTime(1, 1, 1, 10),
            current_turn_id=turn_id,
            completed_world_turn_ids=(),
        )
        reversed_order = selector.select(
            snapshots[1],
            scene_time=SceneTime(1, 1, 1, 10),
            current_turn_id=turn_id,
            completed_world_turn_ids=(),
        )
        assert forward == reversed_order
        assert not isinstance(forward[0], PlotScheduleCandidateBatch)
        selected_pool_ids.append(forward[0].container_id)

    high_count = selected_pool_ids.count(high_pool.id)
    assert 850 <= high_count <= 950
    assert selected_pool_ids.count(low_pool.id) == 1000 - high_count


def test_random_event_weighting_and_soft_batch_are_stable_without_replacement() -> None:
    pool = models.StoryPlotEventPool(
        10,
        1,
        "加权随机池",
        selection_weight=1,
        candidate_batch_size=5,
    )
    events = tuple(
        _event(
            event_id,
            pool.id,
            selection_weight=(9 if event_id == 1 else 1),
        )
        for event_id in range(1, 8)
    )
    snapshot = PlotScheduleSnapshot(
        session_id="weighted-events",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(pool,),
            events=tuple(reversed(events)),
        ),
        overrides=models.SessionPlotOverrides("weighted-events"),
        decisions=(),
    )
    selector = PlotScheduleSelector()
    primary_ids: list[int] = []

    for turn_id in range(1, 1001):
        selected = selector.select(
            snapshot,
            scene_time=SceneTime(1, 1, 1, 10),
            current_turn_id=turn_id,
            completed_world_turn_ids=(),
        )
        repeated = selector.select(
            snapshot,
            scene_time=SceneTime(1, 1, 1, 10),
            current_turn_id=turn_id,
            completed_world_turn_ids=(),
        )
        assert selected == repeated
        batch = selected[0]
        assert isinstance(batch, PlotScheduleCandidateBatch)
        assert batch.configured_size == 5
        assert len(batch.candidates) == 5
        assert batch.candidates[0] == batch.primary
        assert len({candidate.event.id for candidate in batch.candidates}) == 5
        primary_ids.append(batch.primary.event.id)

    weighted_primary_count = primary_ids.count(1)
    assert 530 <= weighted_primary_count <= 670


def test_random_forced_primary_bypasses_soft_batch_construction() -> None:
    event = _event(
        1,
        10,
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
    )
    snapshot = PlotScheduleSnapshot(
        session_id="forced-primary",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(
                models.StoryPlotEventPool(
                    10,
                    1,
                    "强制池",
                    candidate_batch_size=5,
                ),
            ),
            events=(event,),
        ),
        overrides=models.SessionPlotOverrides("forced-primary"),
        decisions=(),
    )

    selected = PlotScheduleSelector().select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    )

    assert len(selected) == 1
    assert not isinstance(selected[0], PlotScheduleCandidateBatch)
    assert selected[0].event.id == event.id


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


def test_pool_cooldown_skips_whole_pool_and_reopens_at_boundary() -> None:
    anchor_event = _event(1, 10, position=0)
    next_high_event = _event(2, 10, position=1)
    low_event = _event(3, 20)
    anchor = _decision(
        1,
        2,
        models.PLOT_SOURCE_POOL,
        anchor_event.id,
        anchor_event.id,
        10,
        models.PLOT_DECISION_TRIGGERED,
        scene_time=SceneTime(1, 1, 1, 10),
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(
                models.StoryPlotEventPool(
                    10,
                    1,
                    "高权重池",
                    selection_mode=models.PLOT_POOL_SEQUENTIAL,
                    selection_weight=100,
                    cooldown_minutes=60,
                ),
                models.StoryPlotEventPool(
                    20,
                    1,
                    "低权重池",
                    selection_weight=1,
                ),
            ),
            events=(anchor_event, next_high_event, low_event),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(anchor,),
    )
    selector = PlotScheduleSelector()

    cooling = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 10, 59),
        current_turn_id=4,
        completed_world_turn_ids=(1, 2, 3),
    )
    ready = selector.select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 11),
        current_turn_id=4,
        completed_world_turn_ids=(1, 2, 3),
    )

    assert [item.event.id for item in cooling] == [low_event.id]
    assert [item.event.id for item in ready] == [next_high_event.id]


def test_pool_cooldown_ignores_manual_outline_deferred_and_error_decisions() -> None:
    event = _event(1, 10)
    available = _event(2, 10)
    manual = _decision(
        4,
        6,
        models.PLOT_SOURCE_POOL,
        event.id,
        event.id,
        10,
        models.PLOT_DECISION_TRIGGERED,
        scene_time=None,
        selection_origin=models.PLOT_SELECTION_ORIGIN_MANUAL,
    )
    outline = _decision(
        3,
        5,
        models.PLOT_SOURCE_OUTLINE,
        51,
        event.id,
        10,
        models.PLOT_DECISION_TRIGGERED,
    )
    deferred = _decision(
        2,
        4,
        models.PLOT_SOURCE_POOL,
        event.id,
        event.id,
        10,
        models.PLOT_DECISION_DEFERRED,
    )
    errored = _decision(
        1,
        3,
        models.PLOT_SOURCE_POOL,
        event.id,
        event.id,
        10,
        models.PLOT_DECISION_ERROR,
    )
    pool = models.StoryPlotEventPool(
        10,
        1,
        "仅有非锚点判断",
        cooldown_minutes=120,
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(pool,),
            events=(event, available),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(manual, outline, deferred, errored),
    )

    diagnostics = evaluate_pool_cooldowns(
        (pool,),
        snapshot.decisions,
        scene_time=SceneTime(1, 1, 1, 8, 1),
    )
    selected = PlotScheduleSelector().select(
        snapshot,
        scene_time=SceneTime(1, 1, 1, 8, 1),
        current_turn_id=7,
        completed_world_turn_ids=(1, 2, 3, 4, 5, 6),
    )

    assert diagnostics[0].status == "ready"
    assert diagnostics[0].anchor is None
    assert [item.event.id for item in selected] == [available.id]


def test_manual_decision_does_not_replace_pool_cooldown_anchor() -> None:
    anchored_event = _event(1, 10)
    pending_event = _event(2, 10)
    scheduler_anchor = _decision(
        1,
        2,
        models.PLOT_SOURCE_POOL,
        anchored_event.id,
        anchored_event.id,
        10,
        models.PLOT_DECISION_TRIGGERED,
        scene_time=SceneTime(1, 1, 1, 8),
    )
    manual = _decision(
        2,
        3,
        models.PLOT_SOURCE_POOL,
        pending_event.id,
        pending_event.id,
        10,
        models.PLOT_DECISION_TRIGGERED,
        scene_time=None,
        selection_origin=models.PLOT_SELECTION_ORIGIN_MANUAL,
    )
    pool = models.StoryPlotEventPool(
        10,
        1,
        "共享冷却池",
        cooldown_minutes=60,
    )

    diagnostic = evaluate_pool_cooldowns(
        (pool,),
        (scheduler_anchor, manual),
        scene_time=SceneTime(1, 1, 1, 8, 30),
    )[0]

    assert diagnostic.status == PLOT_POOL_COOLDOWN_ACTIVE
    assert diagnostic.remaining_minutes == 30
    assert diagnostic.anchor == scheduler_anchor


def test_outline_binding_excludes_event_from_pool_until_all_refs_are_removed() -> None:
    bound = _event(1, 10, position=0)
    free = _event(2, 10, position=1)
    node = models.StoryPlotOutlineNode(
        50,
        1,
        20,
        bound.id,
        SceneTime(1, 1, 1, 9),
        position=0,
        enabled=False,
    )
    pool = models.StoryPlotEventPool(
        10,
        1,
        "顺序池",
        selection_mode=models.PLOT_POOL_SEQUENTIAL,
    )
    bound_snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(pool,),
            events=(bound, free),
            outlines=(
                models.StoryPlotOutline(
                    20,
                    1,
                    "已停用大纲",
                    enabled=False,
                    nodes=(node,),
                ),
            ),
        ),
        overrides=models.SessionPlotOverrides(
            "s1",
            disabled_outline_node_ids=frozenset((node.id,)),
        ),
        decisions=(),
    )
    unbound_snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(pool,),
            events=(bound, free),
            outlines=(),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
    )
    selector = PlotScheduleSelector()

    while_bound = selector.select(
        bound_snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    )
    after_refs_removed = selector.select(
        unbound_snapshot,
        scene_time=SceneTime(1, 1, 1, 10),
        current_turn_id=2,
        completed_world_turn_ids=(1,),
    )

    assert [item.event.id for item in while_bound] == [free.id]
    assert [item.event.id for item in after_refs_removed] == [bound.id]


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
