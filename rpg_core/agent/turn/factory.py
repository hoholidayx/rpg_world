"""Allocate the transaction-bound runtime after the Context gate passes."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rpg_core.agent.telemetry import TurnStats
from rpg_core.agent.turn.transaction import AgentTurnTransaction
from rpg_core.agent.turn.runtime import TurnRuntime

if TYPE_CHECKING:
    from rpg_core.agent.runtime.context import AgentContextService
    from rpg_core.agent.runtime.lifecycle import AgentRuntimeLifecycle
    from rpg_core.agent.runtime.model import MainModelRuntime
    from rpg_core.agent.turn.hooks.fixed import StatusPreflightHook
    from rpg_core.agent.turn.hooks.plot_scheduling import (
        PlotSchedulingPreflightHook,
    )
    from rpg_core.agent.turn.models import TurnExecutionPlan


class TurnRuntimeFactory:
    """Create one turn runtime while enforcing all pre-scratch invariants."""

    def __init__(
        self,
        *,
        lifecycle: "AgentRuntimeLifecycle",
        context_service: "AgentContextService",
        model_runtime: "MainModelRuntime",
        status_preflight: "StatusPreflightHook",
        plot_scheduling_preflight: "PlotSchedulingPreflightHook | None" = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._context_service = context_service
        self._model_runtime = model_runtime
        self._status_preflight = status_preflight
        self._plot_scheduling_preflight = plot_scheduling_preflight

    async def create(self, plan: "TurnExecutionPlan") -> TurnRuntime:
        self._context_service.enforce_window_threshold(
            plan.main_llm,
            rp_module_snapshot=plan.rp_modules,
            turn_execution=plan.execution,
            persistent_memory_snapshot=plan.persistent_memory,
            plot_schedule_snapshot=plan.plot_schedule,
        )
        provider = await self._model_runtime.provider_for(
            self._lifecycle.session_id,
            selection=plan.main_llm,
        )
        stats = TurnStats(started_at=time.monotonic())
        resources = self._lifecycle.resources
        transaction = AgentTurnTransaction(
            session=self._lifecycle.session_manager,
            status_mgr=resources.status_manager,
            scene_tracker=resources.scene_tracker,
        )
        scratch = transaction.begin(stats, mode=plan.request.mode)
        runtime = TurnRuntime(
            plan=plan,
            transaction=transaction,
            scratch=scratch,
            stats=stats,
            provider=provider,
        )
        try:
            registry = self._lifecycle.rp_module_registry
            if registry is not None:
                runtime.rp_module_runtime = registry.create_runtime(plan.rp_modules)
                runtime.rp_module_runtime.bind_turn(scratch)
            if plan.execution.policy.run_status_preflight:
                runtime.preflight_result = await self._status_preflight.run(
                    turn_scratch=scratch,
                    user_input=plan.request.text,
                    turn_stats=stats,
                    rp_module_runtime=runtime.rp_module_runtime,
                    player_character=plan.execution.player_character,
                )
            runtime.preflight_outcome = self._status_preflight.outcome_state(
                scratch,
                runtime.preflight_result,
            )
            if self._plot_scheduling_preflight is not None:
                await self._plot_scheduling_preflight.run(
                    plan=plan,
                    turn_scratch=scratch,
                    turn_stats=stats,
                    rp_module_runtime=runtime.rp_module_runtime,
                )
            return runtime
        except BaseException:
            runtime.discard()
            runtime.close()
            raise
