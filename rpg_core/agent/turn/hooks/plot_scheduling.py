"""Critical plot scheduling preflight between status updates and memory recall."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from rpg_data import models as data_models
from rpg_core.agent.turn.models import TurnMode
from rpg_core.rp_modules.plot_scheduler import PlotScheduleInjection
from rpg_core.rp_modules.plot_scheduler.judge import (
    PlotScheduleJudge,
    build_plot_judge_prompt,
)
from rpg_core.rp_modules.plot_scheduler.models import PlotScheduleCandidate
from rpg_core.rp_modules.plot_scheduler.scheduler import PlotScheduleSelector

if TYPE_CHECKING:
    from rpg_core.agent.runtime.context import AgentContextService
    from rpg_core.agent.telemetry import TurnStats
    from rpg_core.agent.turn.models import TurnExecutionPlan
    from rpg_core.agent.turn.transaction import TurnScratch
    from rpg_core.rp_modules.runtime import RPModuleTurnRuntime
    from rpg_core.session import SessionManager

_TAG = "[PlotSchedulingPreflight]"


class PlotSchedulingPreflightHook:
    """Stage scheduler decisions and injections inside the active turn scratch."""

    def __init__(
        self,
        *,
        context_service: "AgentContextService",
        session_manager: "SessionManager",
        selector: PlotScheduleSelector | None = None,
        judge: PlotScheduleJudge | None = None,
    ) -> None:
        self._context_service = context_service
        self._session_manager = session_manager
        self._selector = selector or PlotScheduleSelector()
        self._judge = judge or PlotScheduleJudge()

    async def run(
        self,
        *,
        plan: "TurnExecutionPlan",
        turn_scratch: "TurnScratch",
        turn_stats: "TurnStats",
        rp_module_runtime: "RPModuleTurnRuntime | None",
    ) -> None:
        snapshot = plan.plot_schedule
        if (
            not snapshot.enabled
            or not plan.execution.policy.expose_rp_modules
            or plan.request.mode is TurnMode.OOC
        ):
            return
        scene_tracker = turn_scratch.scene_tracker
        scene_time = (
            scene_tracker.get_scene_time() if scene_tracker is not None else None
        )
        if scene_time is None:
            error = (
                scene_tracker.scene_time_error
                if scene_tracker is not None
                else "当前 Session 没有 Scene 状态表"
            )
            logger.warning(
                _TAG + " skipped because Scene time is unavailable: session_id={} error={}",
                snapshot.session_id,
                error,
            )
            return

        candidates = self._selector.select(
            snapshot,
            scene_time=scene_time,
            current_turn_id=turn_scratch.turn_id,
            completed_ic_gm_turn_ids=self._completed_ic_gm_turn_ids(
                turn_scratch.base_history
            ),
        )
        for candidate in candidates:
            await self._stage_candidate(
                plan=plan,
                turn_scratch=turn_scratch,
                turn_stats=turn_stats,
                rp_module_runtime=rp_module_runtime,
                candidate=candidate,
                scene_time=scene_time,
            )

    async def _stage_candidate(
        self,
        *,
        plan: "TurnExecutionPlan",
        turn_scratch: "TurnScratch",
        turn_stats: "TurnStats",
        rp_module_runtime: "RPModuleTurnRuntime | None",
        candidate: PlotScheduleCandidate,
        scene_time,
    ) -> None:
        if candidate.dispatch_mode == data_models.PLOT_DISPATCH_FORCED:
            reason = "已达到 Scene 时间，按强制模式触发。"
            self._stage_triggered(turn_scratch, candidate, scene_time, reason)
            return

        try:
            prompt = build_plot_judge_prompt(
                candidate,
                accepted_injections=tuple(turn_scratch.plot_schedule_injections),
            )
            messages = self._context_service.build_plot_judge_messages(
                judge_prompt=prompt,
                current_user_input=plan.request.text,
                history_turns=plan.plot_schedule.judge_history_turns,
                status_manager=turn_scratch.status_manager,
                scene_tracker=turn_scratch.scene_tracker,
                rp_module_runtime=rp_module_runtime,
                turn_execution=plan.execution,
            )
            judgment = await self._judge.judge(messages, turn_stats=turn_stats)
        except Exception as exc:
            logger.opt(exception=exc).warning(
                _TAG + " soft judgment failed: source={} source_id={}",
                candidate.source_kind,
                candidate.source_id,
            )
            turn_scratch.plot_schedule_decisions.append(
                self._decision(
                    candidate,
                    scene_time,
                    status=data_models.PLOT_DECISION_ERROR,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            return
        if judgment.suitable:
            self._stage_triggered(
                turn_scratch,
                candidate,
                scene_time,
                judgment.reason,
            )
            return
        turn_scratch.plot_schedule_decisions.append(
            self._decision(
                candidate,
                scene_time,
                status=data_models.PLOT_DECISION_DEFERRED,
                reason=judgment.reason,
            )
        )

    def _stage_triggered(
        self,
        turn_scratch: "TurnScratch",
        candidate: PlotScheduleCandidate,
        scene_time,
        reason: str,
    ) -> None:
        turn_scratch.plot_schedule_injections.append(
            PlotScheduleInjection(
                source_kind=candidate.source_kind,
                source_id=candidate.source_id,
                event_id=candidate.event.id,
                container_id=candidate.container_id,
                container_name=candidate.container_name,
                event_title=candidate.event.title,
                directive=candidate.event.directive,
                dispatch_mode=candidate.dispatch_mode,
                scene_time=scene_time,
                reason=reason,
            )
        )
        turn_scratch.plot_schedule_decisions.append(
            self._decision(
                candidate,
                scene_time,
                status=data_models.PLOT_DECISION_TRIGGERED,
                reason=reason,
            )
        )

    @staticmethod
    def _decision(
        candidate: PlotScheduleCandidate,
        scene_time,
        *,
        status: str,
        reason: str = "",
        error_code: str = "",
        error_message: str = "",
    ) -> data_models.StagedPlotScheduleDecision:
        snapshot = {
            "sourceKind": candidate.source_kind,
            "sourceId": candidate.source_id,
            "containerId": candidate.container_id,
            "containerName": candidate.container_name,
            "eventId": candidate.event.id,
            "eventTitle": candidate.event.title,
            "eventDescription": candidate.event.description,
            "directive": candidate.event.directive,
            "suitabilityHint": candidate.event.suitability_hint,
            "scheduledTime": (
                candidate.scheduled_time.to_dict()
                if candidate.scheduled_time is not None
                else None
            ),
            "dispatchMode": candidate.dispatch_mode,
            "eventVersion": candidate.event.version,
        }
        return data_models.StagedPlotScheduleDecision(
            source_kind=candidate.source_kind,
            source_id=candidate.source_id,
            event_id=candidate.event.id,
            container_id=candidate.container_id,
            decision_status=status,
            dispatch_mode=candidate.dispatch_mode,
            scene_time=scene_time,
            event_snapshot=snapshot,
            reason=reason,
            error_code=error_code,
            error_message=error_message,
        )

    def _completed_ic_gm_turn_ids(self, messages) -> tuple[int, ...]:
        groups = self._session_manager.iter_turn_groups(
            [
                message
                for message in messages
                if not message.is_system() and not message.is_tool()
            ]
        )
        completed: list[int] = []
        for group in groups:
            modes = {str(message.mode or TurnMode.IC.value).lower() for message in group}
            if not modes or not modes.issubset({TurnMode.IC.value, TurnMode.GM.value}):
                continue
            turn_id = next((message.turn_id for message in group if message.turn_id > 0), 0)
            if turn_id > 0:
                completed.append(turn_id)
        return tuple(completed)
