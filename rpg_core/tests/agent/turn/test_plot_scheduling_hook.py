from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from commons.scene_time import SceneTime
from llm_client.client import LLMProviderContractError
from rpg_data import models
from rpg_core.agent.telemetry import TurnStats
from rpg_core.agent.turn.hooks.plot_scheduling import PlotSchedulingPreflightHook
from rpg_core.agent.turn.models import (
    TurnExecutionPlan,
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnRequest,
)
from rpg_core.context.models import Message, Role
from rpg_core.rp_modules.plot_scheduler import (
    PlotPendingInjectionTurnState,
    PlotSceneOpportunityTurnState,
    PlotScheduleSnapshot,
    PlotSuitabilityDecision,
)
from rpg_core.session.modes import TurnMode


class _Scene:
    scene_time_error = ""

    @staticmethod
    def get_scene_time() -> SceneTime:
        return SceneTime(1, 1, 1, 10)


class _Context:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_plot_judge_messages(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        return [Message(Role.SYSTEM, "fixed"), Message(Role.USER, "行动")]


class _Judge:
    def __init__(self, result: PlotSuitabilityDecision | BaseException) -> None:
        self.result = result
        self.calls = 0

    async def judge(self, _messages, *, turn_stats):  # noqa: ANN001, ANN201
        del turn_stats
        self.calls += 1
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _plan(
    dispatch_mode: str = models.PLOT_DISPATCH_SOFT,
    *,
    deadline_time: SceneTime | None = None,
    mode: TurnMode = TurnMode.NEUTRAL,
    with_scene_opportunity: bool = True,
) -> TurnExecutionPlan:
    event = models.StoryPlotEvent(
        id=10,
        story_id=1,
        pool_id=20,
        title="雨夜来信",
        directive="让信使送来一封信。",
        dispatch_mode=dispatch_mode,
        deadline_time=deadline_time,
    )
    snapshot = PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(models.StoryPlotEventPool(20, 1, "主池"),),
            events=(event,),
        ),
        overrides=models.SessionPlotOverrides("s1"),
        decisions=(),
        scene_opportunity=(
            models.SessionPlotSceneOpportunity(
                session_id="s1",
                source_turn_id=1,
                version=3,
            )
            if with_scene_opportunity
            else None
        ),
    )
    request = TurnRequest.create("我推开门", mode=mode)
    return TurnExecutionPlan(
        execution=TurnExecutionSnapshot(
            request=request,
            narrative_style_id=None,
            narrative_style_name="",
            narrative_style_prompt="",
            policy=TurnExecutionPolicy.for_mode(request.mode),
        ),
        main_llm=SimpleNamespace(),
        rp_modules=SimpleNamespace(),
        plot_schedule=snapshot,
    )


def _scratch(*, with_scene_opportunity: bool = True):  # noqa: ANN201
    opportunity = (
        models.SessionPlotSceneOpportunity(
            session_id="s1",
            source_turn_id=1,
            version=3,
        )
        if with_scene_opportunity
        else None
    )
    return SimpleNamespace(
        turn_id=2,
        base_history=[],
        scene_tracker=_Scene(),
        status_manager=None,
        plot_schedule_decisions=[],
        plot_schedule_injections=[],
        plot_scene_opportunity=(
            PlotSceneOpportunityTurnState(base=opportunity)
            if opportunity is not None
            else PlotSceneOpportunityTurnState()
        ),
    )


@pytest.mark.asyncio
async def test_soft_plot_candidate_stages_trigger_and_dynamic_injection() -> None:
    context = _Context()
    judge = _Judge(PlotSuitabilityDecision(True, "人物与地点均满足。"))
    hook = PlotSchedulingPreflightHook(
        context_service=context,
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )
    scratch = _scratch()

    await hook.run(
        plan=_plan(deadline_time=SceneTime(1, 1, 1, 12)),
        turn_scratch=scratch,
        turn_stats=TurnStats(),
        rp_module_runtime=None,
    )

    assert judge.calls == 1
    assert len(context.calls) == 1
    assert scratch.plot_schedule_decisions[0].decision_status == "triggered"
    assert scratch.plot_schedule_decisions[0].event_snapshot["deadlineTime"] == {
        "year": 1,
        "month": 1,
        "day": 1,
        "hour": 12,
        "minute": 0,
    }
    assert scratch.plot_schedule_injections[0].directive == "让信使送来一封信。"
    assert scratch.plot_scene_opportunity.consume_base is True


@pytest.mark.asyncio
async def test_soft_plot_judge_error_is_staged_without_raising() -> None:
    hook = PlotSchedulingPreflightHook(
        context_service=_Context(),
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=_Judge(RuntimeError("judge unavailable")),
    )
    scratch = _scratch()

    await hook.run(
        plan=_plan(),
        turn_scratch=scratch,
        turn_stats=TurnStats(),
        rp_module_runtime=None,
    )

    assert scratch.plot_schedule_injections == []
    assert scratch.plot_schedule_decisions[0].decision_status == "error"
    assert scratch.plot_schedule_decisions[0].error_code == "RuntimeError"
    assert scratch.plot_scene_opportunity.consume_base is True


@pytest.mark.asyncio
async def test_soft_plot_contract_error_is_not_staged_as_a_soft_failure() -> None:
    hook = PlotSchedulingPreflightHook(
        context_service=_Context(),
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=_Judge(LLMProviderContractError("contract failure")),
    )
    scratch = _scratch()

    with pytest.raises(LLMProviderContractError):
        await hook.run(
            plan=_plan(),
            turn_scratch=scratch,
            turn_stats=TurnStats(),
            rp_module_runtime=None,
        )

    assert scratch.plot_schedule_injections == []
    assert scratch.plot_schedule_decisions == []
    # Opportunity consumption is staged before adjudication, but the
    # orchestrator discards this entire scratch when the contract error escapes.
    assert scratch.plot_scene_opportunity.consume_base is True


@pytest.mark.asyncio
async def test_forced_plot_candidate_never_calls_judge() -> None:
    judge = _Judge(AssertionError("forced scheduling must not call LLM"))
    hook = PlotSchedulingPreflightHook(
        context_service=_Context(),
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )
    scratch = _scratch()

    await hook.run(
        plan=_plan(models.PLOT_DISPATCH_FORCED),
        turn_scratch=scratch,
        turn_stats=TurnStats(),
        rp_module_runtime=None,
    )

    assert judge.calls == 0
    assert scratch.plot_schedule_decisions[0].decision_status == "triggered"
    assert len(scratch.plot_schedule_injections) == 1
    assert scratch.plot_scene_opportunity.consume_base is True


@pytest.mark.asyncio
async def test_ooc_turn_never_calls_judge_or_stages_a_decision() -> None:
    context = _Context()
    judge = _Judge(AssertionError("OOC must not reach the plot judge"))
    hook = PlotSchedulingPreflightHook(
        context_service=context,
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )
    scratch = _scratch()

    await hook.run(
        plan=_plan(models.PLOT_DISPATCH_FORCED, mode=TurnMode.OOC),
        turn_scratch=scratch,
        turn_stats=TurnStats(),
        rp_module_runtime=None,
    )

    assert judge.calls == 0
    assert context.calls == []
    assert scratch.plot_schedule_injections == []
    assert scratch.plot_schedule_decisions == []
    assert scratch.plot_scene_opportunity.consume_base is False


@pytest.mark.asyncio
async def test_expired_plot_candidate_never_calls_judge_or_stages_a_decision() -> None:
    context = _Context()
    judge = _Judge(AssertionError("expired event must not reach the judge"))
    hook = PlotSchedulingPreflightHook(
        context_service=context,
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )
    scratch = _scratch()

    await hook.run(
        plan=_plan(deadline_time=SceneTime(1, 1, 1, 10)),
        turn_scratch=scratch,
        turn_stats=TurnStats(),
        rp_module_runtime=None,
    )

    assert judge.calls == 0
    assert context.calls == []
    assert scratch.plot_schedule_injections == []
    assert scratch.plot_schedule_decisions == []
    assert scratch.plot_scene_opportunity.consume_base is True


@pytest.mark.asyncio
async def test_turn_without_prior_scene_change_never_selects_or_judges() -> None:
    context = _Context()
    judge = _Judge(AssertionError("turn without Scene opportunity must not judge"))
    hook = PlotSchedulingPreflightHook(
        context_service=context,
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )
    scratch = _scratch(with_scene_opportunity=False)

    await hook.run(
        plan=_plan(with_scene_opportunity=False),
        turn_scratch=scratch,
        turn_stats=TurnStats(),
    )

    assert judge.calls == 0
    assert context.calls == []
    assert scratch.plot_schedule_injections == []
    assert scratch.plot_schedule_decisions == []
    assert scratch.plot_scene_opportunity.dirty is False


@pytest.mark.asyncio
async def test_scene_opportunity_is_consumed_when_scene_time_is_unavailable() -> None:
    judge = _Judge(AssertionError("invalid Scene time must not reach judge"))
    hook = PlotSchedulingPreflightHook(
        context_service=_Context(),
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )
    scratch = _scratch()
    scratch.scene_tracker = SimpleNamespace(
        get_scene_time=lambda: None,
        scene_time_error="时间格式非法",
    )

    await hook.run(
        plan=_plan(),
        turn_scratch=scratch,
        turn_stats=TurnStats(),
    )

    assert judge.calls == 0
    assert scratch.plot_schedule_decisions == []
    assert scratch.plot_scene_opportunity.consume_base is True


@pytest.mark.asyncio
async def test_manual_pending_injection_bypasses_scene_and_uses_frozen_snapshot() -> None:
    pending = models.SessionPlotPendingInjection(
        session_id="s1",
        story_id=1,
        source_event_id=999,
        source_event_version=7,
        source_pool_id=88,
        source_pool_name="已删除池",
        event_title="临时标题",
        directive="临时强制指令。",
        event_snapshot={
            "originalEventTitle": "原标题",
            "originalDirective": "原指令。",
        },
        requested_turn_id=1,
        version=3,
    )
    plan = _plan(with_scene_opportunity=False)
    plan = replace(
        plan,
        plot_schedule=replace(
            plan.plot_schedule,
            pending_injection=pending,
        ),
    )
    scratch = _scratch(with_scene_opportunity=False)
    scratch.scene_tracker = SimpleNamespace(
        get_scene_time=lambda: None,
        scene_time_error="没有 Scene",
    )
    scratch.plot_pending_injection = PlotPendingInjectionTurnState(base=pending)
    judge = _Judge(PlotSuitabilityDecision(True, "不应调用"))
    hook = PlotSchedulingPreflightHook(
        context_service=_Context(),
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )

    await hook.run(
        plan=plan,
        turn_scratch=scratch,
        turn_stats=TurnStats(),
    )

    assert judge.calls == 0
    assert len(scratch.plot_schedule_injections) == 1
    injection = scratch.plot_schedule_injections[0]
    assert injection.event_id == 999
    assert injection.event_title == "临时标题"
    assert injection.directive == "临时强制指令。"
    assert injection.scene_time is None
    decision = scratch.plot_schedule_decisions[0]
    assert decision.selection_origin == models.PLOT_SELECTION_ORIGIN_MANUAL
    assert decision.scene_time is None
    assert decision.event_snapshot["eventTitle"] == "临时标题"
    assert scratch.plot_pending_injection.consume_base is True
    assert scratch.plot_scene_opportunity.consume_base is False


@pytest.mark.asyncio
async def test_manual_pending_replaces_pool_lane_and_ooc_does_not_consume() -> None:
    pending = models.SessionPlotPendingInjection(
        session_id="s1",
        story_id=1,
        source_event_id=10,
        source_event_version=1,
        source_pool_id=20,
        source_pool_name="主池",
        event_title="手动标题",
        directive="手动指令。",
        event_snapshot={},
        requested_turn_id=1,
    )
    plan = _plan(models.PLOT_DISPATCH_SOFT)
    plan = replace(
        plan,
        plot_schedule=replace(plan.plot_schedule, pending_injection=pending),
    )
    scratch = _scratch()
    scratch.plot_pending_injection = PlotPendingInjectionTurnState(base=pending)
    judge = _Judge(PlotSuitabilityDecision(True, "不应调用自动池 Judge"))
    hook = PlotSchedulingPreflightHook(
        context_service=_Context(),
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )

    await hook.run(
        plan=plan,
        turn_scratch=scratch,
        turn_stats=TurnStats(),
    )
    assert judge.calls == 0
    assert [item.event_title for item in scratch.plot_schedule_injections] == [
        "手动标题"
    ]
    assert scratch.plot_scene_opportunity.consume_base is True

    ooc_plan = replace(
        plan,
        execution=replace(
            plan.execution,
            request=TurnRequest.create("场外继续", mode=TurnMode.OOC),
            policy=TurnExecutionPolicy.for_mode(TurnMode.OOC),
        ),
    )
    ooc_scratch = _scratch()
    ooc_scratch.plot_pending_injection = PlotPendingInjectionTurnState(
        base=pending
    )
    await hook.run(
        plan=ooc_plan,
        turn_scratch=ooc_scratch,
        turn_stats=TurnStats(),
    )
    assert ooc_scratch.plot_schedule_injections == []
    assert ooc_scratch.plot_pending_injection.consume_base is False
    assert ooc_scratch.plot_scene_opportunity.consume_base is False


@pytest.mark.asyncio
async def test_manual_pending_keeps_distinct_outline_lane_on_scene_opportunity() -> None:
    pending = models.SessionPlotPendingInjection(
        session_id="s1",
        story_id=1,
        source_event_id=10,
        source_event_version=1,
        source_pool_id=20,
        source_pool_name="主池",
        event_title="手动池事件",
        directive="执行手动池事件。",
        requested_turn_id=1,
    )
    plan = _plan()
    outline_event = models.StoryPlotEvent(
        id=11,
        story_id=1,
        pool_id=20,
        title="独立大纲事件",
        directive="执行独立大纲事件。",
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
    )
    node = models.StoryPlotOutlineNode(
        id=30,
        story_id=1,
        outline_id=40,
        event_id=outline_event.id,
        scheduled_time=SceneTime(1, 1, 1, 9),
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
    )
    plan = replace(
        plan,
        plot_schedule=replace(
            plan.plot_schedule,
            story=replace(
                plan.plot_schedule.story,
                events=(*plan.plot_schedule.story.events, outline_event),
                outlines=(
                    models.StoryPlotOutline(
                        id=40,
                        story_id=1,
                        name="主线",
                        nodes=(node,),
                    ),
                ),
            ),
            pending_injection=pending,
        ),
    )
    scratch = _scratch()
    scratch.plot_pending_injection = PlotPendingInjectionTurnState(base=pending)
    judge = _Judge(AssertionError("forced outline and manual pool must not judge"))
    hook = PlotSchedulingPreflightHook(
        context_service=_Context(),
        session_manager=SimpleNamespace(iter_turn_groups=lambda messages: []),
        judge=judge,
    )

    await hook.run(
        plan=plan,
        turn_scratch=scratch,
        turn_stats=TurnStats(),
    )

    assert judge.calls == 0
    assert [
        item.event_title for item in scratch.plot_schedule_injections
    ] == ["手动池事件", "独立大纲事件"]
    assert [
        item.source_kind for item in scratch.plot_schedule_decisions
    ] == [models.PLOT_SOURCE_POOL, models.PLOT_SOURCE_OUTLINE]
    assert scratch.plot_scene_opportunity.consume_base is True
