from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from commons.scene_time import SceneTime
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


def _scratch():  # noqa: ANN201
    return SimpleNamespace(
        turn_id=2,
        base_history=[],
        scene_tracker=_Scene(),
        status_manager=None,
        plot_schedule_decisions=[],
        plot_schedule_injections=[],
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
    plan = _plan()
    plan = replace(
        plan,
        plot_schedule=replace(
            plan.plot_schedule,
            pending_injection=pending,
        ),
    )
    scratch = _scratch()
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
