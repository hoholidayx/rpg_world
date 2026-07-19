"""Resolve all immutable selections before allocating turn scratch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.agent.turn.models import TurnExecutionPlan, TurnRequest
from rpg_core.rp_modules.plot_scheduler import PlotScheduleSnapshotResolver

if TYPE_CHECKING:
    from rpg_core.agent.runtime.context import AgentContextService
    from rpg_core.agent.runtime.lifecycle import AgentRuntimeLifecycle
    from rpg_core.agent.runtime.model import MainModelRuntime


class TurnPlanResolver:
    """Combine mode/style, main-model, and RP-module snapshots."""

    def __init__(
        self,
        *,
        lifecycle: "AgentRuntimeLifecycle",
        context_service: "AgentContextService",
        model_runtime: "MainModelRuntime",
        plot_schedule_resolver: PlotScheduleSnapshotResolver | None = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._context_service = context_service
        self._model_runtime = model_runtime
        self._plot_schedule_resolver = (
            plot_schedule_resolver or PlotScheduleSnapshotResolver()
        )

    async def resolve(self, request: TurnRequest) -> TurnExecutionPlan:
        execution = self._context_service.resolve_turn_execution(
            request,
            require_player_character=True,
        )
        rp_modules = self._context_service.resolve_rp_module_snapshot()
        return TurnExecutionPlan(
            execution=execution,
            main_llm=await self._model_runtime.resolve(self._lifecycle.session_id),
            rp_modules=rp_modules,
            plot_schedule=self._plot_schedule_resolver.resolve(
                self._lifecycle.session_id,
                rp_modules,
            ),
            persistent_memory=(
                await self._context_service.load_persistent_memory_snapshot()
            ),
        )
