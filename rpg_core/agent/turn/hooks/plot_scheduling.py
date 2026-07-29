"""Critical plot scheduling preflight between status updates and memory recall."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from llm_client.client import LLMProviderContractError
from rpg_data import models as data_models
from rpg_core.session.modes import (
    DEFAULT_TURN_MODE,
    WORLD_ADVANCING_MODES,
    is_world_advancing_mode,
)
from rpg_core.rp_modules.plot_scheduler import PlotScheduleInjection
from rpg_core.rp_modules.plot_scheduler.judge import (
    PlotScheduleJudge,
    PlotScheduleJudgeResponseError,
    build_plot_judge_prompt,
)
from rpg_core.rp_modules.plot_scheduler.models import (
    PlotScheduleCandidate,
    PlotScheduleCandidateBatch,
)
from rpg_core.rp_modules.plot_scheduler.scheduler import PlotScheduleSelector

if TYPE_CHECKING:
    from rpg_core.agent.runtime.context import AgentContextService
    from rpg_core.agent.telemetry import TurnStats
    from rpg_core.agent.tools.lookup import LookupToolSet
    from rpg_core.agent.turn.models import TurnExecutionPlan
    from rpg_core.agent.turn.transaction import TurnScratch
    from rpg_core.session import SessionManager

_TAG = "[PlotSchedulingPreflight]"


class PlotSchedulingPreflightHook:
    """Stage scheduler decisions and injections inside the active turn scratch."""

    def __init__(
        self,
        *,
        context_service: "AgentContextService",
        session_manager: "SessionManager",
        lookup_tools: "LookupToolSet | None" = None,
        selector: PlotScheduleSelector | None = None,
        judge: PlotScheduleJudge | None = None,
    ) -> None:
        self._context_service = context_service
        self._session_manager = session_manager
        self._selector = selector or PlotScheduleSelector()
        self._judge = judge or PlotScheduleJudge(lookup_tools=lookup_tools)

    async def run(
        self,
        *,
        plan: "TurnExecutionPlan",
        turn_scratch: "TurnScratch",
        turn_stats: "TurnStats",
        rp_module_runtime: object | None = None,
    ) -> None:
        # Kept as a compatibility-only argument. Generic RP Module fixed/runtime
        # content is intentionally never read by Plot adjudication.
        del rp_module_runtime
        snapshot = plan.plot_schedule
        if (
            not snapshot.enabled
            or not plan.execution.policy.expose_rp_modules
            or not is_world_advancing_mode(plan.request.mode)
        ):
            return
        manual_event_id: int | None = None
        if snapshot.pending_injection is not None:
            manual_event_id = snapshot.pending_injection.source_event_id
            self._stage_manual_injection(
                turn_scratch,
                snapshot.pending_injection,
                (
                    turn_scratch.scene_tracker.get_scene_time()
                    if turn_scratch.scene_tracker is not None
                    else None
                ),
            )
        scene_opportunity = turn_scratch.plot_scene_opportunity
        if snapshot.scene_opportunity is None:
            return
        if scene_opportunity is None or not scene_opportunity.available:
            raise RuntimeError("Plot Scene opportunity scratch state is missing")
        scene_opportunity.consume()

        scene_tracker = turn_scratch.scene_tracker
        scene_time = (
            scene_tracker.get_scene_time() if scene_tracker is not None else None
        )
        if scene_time is None:
            if manual_event_id is not None:
                logger.info(
                    _TAG + " manual injection bypassed unavailable Scene time: session_id={} event_id={}",
                    snapshot.session_id,
                    manual_event_id,
                )
                return
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
            completed_world_turn_ids=self._completed_world_turn_ids(
                turn_scratch.base_history
            ),
        )
        for selected in candidates:
            primary = (
                selected.primary
                if isinstance(selected, PlotScheduleCandidateBatch)
                else selected
            )
            if manual_event_id is not None and (
                primary.source_kind == data_models.PLOT_SOURCE_POOL
                or primary.event.id == manual_event_id
            ):
                continue
            if isinstance(selected, PlotScheduleCandidateBatch):
                await self._stage_candidate_batch(
                    plan=plan,
                    turn_scratch=turn_scratch,
                    turn_stats=turn_stats,
                    batch=selected,
                    scene_time=scene_time,
                )
            else:
                await self._stage_candidate(
                    plan=plan,
                    turn_scratch=turn_scratch,
                    turn_stats=turn_stats,
                    candidate=selected,
                    scene_time=scene_time,
                )

    def _stage_manual_injection(
        self,
        turn_scratch: "TurnScratch",
        pending: data_models.SessionPlotPendingInjection,
        scene_time,
    ) -> None:
        turn_scratch.plot_schedule_injections.append(
            PlotScheduleInjection(
                source_kind=data_models.PLOT_SOURCE_POOL,
                source_id=pending.source_event_id,
                event_id=pending.source_event_id,
                container_id=pending.source_pool_id,
                container_name=pending.source_pool_name,
                event_title=pending.event_title,
                directive=pending.directive,
                dispatch_mode=data_models.PLOT_DISPATCH_FORCED,
                scene_time=scene_time,
                reason="用户已手动标记为下一次非 OOC turn 强制注入。",
            )
        )
        event_snapshot = dict(pending.event_snapshot)
        event_snapshot.update({
            "sourceKind": data_models.PLOT_SOURCE_POOL,
            "sourceId": pending.source_event_id,
            "containerId": pending.source_pool_id,
            "containerName": pending.source_pool_name,
            "eventId": pending.source_event_id,
            "eventTitle": pending.event_title,
            "directive": pending.directive,
            "dispatchMode": data_models.PLOT_DISPATCH_FORCED,
            "eventVersion": pending.source_event_version,
            "selectionOrigin": data_models.PLOT_SELECTION_ORIGIN_MANUAL,
        })
        turn_scratch.plot_schedule_decisions.append(
            data_models.StagedPlotScheduleDecision(
                source_kind=data_models.PLOT_SOURCE_POOL,
                source_id=pending.source_event_id,
                event_id=pending.source_event_id,
                container_id=pending.source_pool_id,
                decision_status=data_models.PLOT_DECISION_TRIGGERED,
                dispatch_mode=data_models.PLOT_DISPATCH_FORCED,
                scene_time=scene_time,
                event_snapshot=event_snapshot,
                selection_origin=data_models.PLOT_SELECTION_ORIGIN_MANUAL,
                reason="用户手动标记的一次性事件注入。",
            )
        )
        if turn_scratch.plot_pending_injection is None:
            raise RuntimeError("manual Plot injection scratch state is missing")
        turn_scratch.plot_pending_injection.consume()

    async def _stage_candidate(
        self,
        *,
        plan: "TurnExecutionPlan",
        turn_scratch: "TurnScratch",
        turn_stats: "TurnStats",
        candidate: PlotScheduleCandidate,
        scene_time,
    ) -> None:
        if candidate.dispatch_mode == data_models.PLOT_DISPATCH_FORCED:
            reason = "已达到 Scene 时间，按强制模式触发。"
            self._stage_triggered(turn_scratch, candidate, scene_time, reason)
            return
        await self._stage_soft_candidates(
            plan=plan,
            turn_scratch=turn_scratch,
            turn_stats=turn_stats,
            primary=candidate,
            candidates=(candidate,),
            configured_batch_size=1,
            scene_time=scene_time,
        )

    async def _stage_candidate_batch(
        self,
        *,
        plan: "TurnExecutionPlan",
        turn_scratch: "TurnScratch",
        turn_stats: "TurnStats",
        batch: PlotScheduleCandidateBatch,
        scene_time,
    ) -> None:
        if any(
            candidate.dispatch_mode != data_models.PLOT_DISPATCH_SOFT
            for candidate in batch.candidates
        ):
            raise RuntimeError("Plot rerank batch must contain only soft candidates")
        await self._stage_soft_candidates(
            plan=plan,
            turn_scratch=turn_scratch,
            turn_stats=turn_stats,
            primary=batch.primary,
            candidates=batch.candidates,
            configured_batch_size=batch.configured_size,
            scene_time=scene_time,
        )

    async def _stage_soft_candidates(
        self,
        *,
        plan: "TurnExecutionPlan",
        turn_scratch: "TurnScratch",
        turn_stats: "TurnStats",
        primary: PlotScheduleCandidate,
        candidates: tuple[PlotScheduleCandidate, ...],
        configured_batch_size: int,
        scene_time,
    ) -> None:
        selection_context = self._selection_context(
            primary=primary,
            candidates=candidates,
            configured_batch_size=configured_batch_size,
        )
        try:
            prompt = build_plot_judge_prompt(
                candidates,
                primary_event_id=primary.event.id,
                accepted_injections=tuple(turn_scratch.plot_schedule_injections),
            )
            messages = self._context_service.build_plot_judge_messages(
                judge_prompt=prompt,
                current_user_input=plan.request.text,
                history_turns=plan.plot_schedule.judge_history_turns,
                status_manager=turn_scratch.status_manager,
                scene_tracker=turn_scratch.scene_tracker,
                adjudication_context=plan.adjudication_context,
            )
            judgment = await self._judge.judge(messages, turn_stats=turn_stats)
            selected = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.event.id == judgment.selected_event_id
                ),
                None,
            )
            if selected is None:
                raise PlotScheduleJudgeResponseError(
                    "selectedEventId must identify an event in the candidate batch"
                )
        except LLMProviderContractError:
            raise
        except Exception as exc:
            logger.opt(exception=exc).warning(
                _TAG + " soft judgment failed: source={} source_id={}",
                primary.source_kind,
                primary.source_id,
            )
            turn_scratch.plot_schedule_decisions.append(
                self._decision(
                    primary,
                    scene_time,
                    status=data_models.PLOT_DECISION_ERROR,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    selection_context=selection_context,
                )
            )
            return
        if judgment.suitable:
            self._stage_triggered(
                turn_scratch,
                selected,
                scene_time,
                judgment.reason,
                selection_context=selection_context,
            )
            return
        turn_scratch.plot_schedule_decisions.append(
            self._decision(
                selected,
                scene_time,
                status=data_models.PLOT_DECISION_DEFERRED,
                reason=judgment.reason,
                selection_context=selection_context,
            )
        )

    def _stage_triggered(
        self,
        turn_scratch: "TurnScratch",
        candidate: PlotScheduleCandidate,
        scene_time,
        reason: str,
        *,
        selection_context: dict[str, object] | None = None,
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
                selection_context=selection_context,
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
        selection_context: dict[str, object] | None = None,
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
            "deadlineTime": (
                candidate.event.deadline_time.to_dict()
                if candidate.event.deadline_time is not None
                else None
            ),
            "dispatchMode": candidate.dispatch_mode,
            "eventVersion": candidate.event.version,
            "containerPriority": candidate.container_priority,
            "containerSelectionWeight": candidate.container_selection_weight,
            "eventSelectionWeight": candidate.event_selection_weight,
            "selectionContext": (
                dict(selection_context)
                if selection_context is not None
                else PlotSchedulingPreflightHook._selection_context(
                    primary=candidate,
                    candidates=(candidate,),
                    configured_batch_size=1,
                )
            ),
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

    @staticmethod
    def _selection_context(
        *,
        primary: PlotScheduleCandidate,
        candidates: tuple[PlotScheduleCandidate, ...],
        configured_batch_size: int,
    ) -> dict[str, object]:
        if primary.source_kind == data_models.PLOT_SOURCE_OUTLINE:
            method = "outline_priority"
        elif primary.pool_selection_mode == data_models.PLOT_POOL_SEQUENTIAL:
            method = "sequential"
        elif primary.dispatch_mode == data_models.PLOT_DISPATCH_FORCED:
            method = "weighted_primary_forced"
        else:
            method = "weighted_batch_rerank"
        return {
            "method": method,
            "primaryEventId": primary.event.id,
            "configuredBatchSize": configured_batch_size,
            "actualBatchSize": len(candidates),
            "candidates": [
                {
                    "eventId": candidate.event.id,
                    "eventTitle": candidate.event.title,
                    "selectionWeight": candidate.event_selection_weight,
                }
                for candidate in candidates
            ],
        }

    def _completed_world_turn_ids(self, messages) -> tuple[int, ...]:
        groups = self._session_manager.iter_turn_groups(
            [
                message
                for message in messages
                if not message.is_system() and not message.is_tool()
            ]
        )
        completed: list[int] = []
        for group in groups:
            modes = {
                str(message.mode or DEFAULT_TURN_MODE.value).lower()
                for message in group
            }
            if not modes or not modes.issubset(
                {mode.value for mode in WORLD_ADVANCING_MODES}
            ):
                continue
            turn_id = next((message.turn_id for message in group if message.turn_id > 0), 0)
            if turn_id > 0:
                completed.append(turn_id)
        return tuple(completed)
