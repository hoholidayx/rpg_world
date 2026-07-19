from __future__ import annotations

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
    PlotScheduleSnapshot,
    PlotSuitabilityDecision,
)


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


def _plan(dispatch_mode: str = models.PLOT_DISPATCH_SOFT) -> TurnExecutionPlan:
    event = models.StoryPlotEvent(
        id=10,
        story_id=1,
        pool_id=20,
        title="雨夜来信",
        directive="让信使送来一封信。",
        dispatch_mode=dispatch_mode,
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
    request = TurnRequest.create("我推开门")
    return TurnExecutionPlan(
        execution=TurnExecutionSnapshot(
            request=request,
            mode_prompt="",
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
        plan=_plan(),
        turn_scratch=scratch,
        turn_stats=TurnStats(),
        rp_module_runtime=None,
    )

    assert judge.calls == 1
    assert len(context.calls) == 1
    assert scratch.plot_schedule_decisions[0].decision_status == "triggered"
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
