"""Resolve all immutable selections before allocating turn scratch."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rpg_core.agent.turn.models import TurnExecutionPlan, TurnRequest
from rpg_core.rp_modules.message_mode import ensure_message_mode_available
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
        plot_schedule_resolver: PlotScheduleSnapshotResolver,
    ) -> None:
        self._lifecycle = lifecycle
        self._context_service = context_service
        self._model_runtime = model_runtime
        self._plot_schedule_resolver = plot_schedule_resolver

    async def resolve(self, request: TurnRequest) -> TurnExecutionPlan:
        rp_modules = self._context_service.resolve_rp_module_snapshot()
        ensure_message_mode_available(rp_modules, request.mode)
        execution = self._context_service.resolve_turn_execution(
            request,
            require_player_character=True,
        )
        (
            main_llm,
            persistent_memory,
            story_memory,
        ) = await asyncio.gather(
            self._model_runtime.resolve(self._lifecycle.session_id),
            self._context_service.load_persistent_memory_snapshot(),
            self._context_service.load_story_memory_snapshot(),
        )
        return TurnExecutionPlan(
            execution=execution,
            main_llm=main_llm,
            rp_modules=rp_modules,
            plot_schedule=self._plot_schedule_resolver.resolve(
                self._lifecycle.session_id,
                rp_modules,
            ),
            persistent_memory=persistent_memory,
            story_memory=story_memory,
            adjudication_context=(
                self._context_service.build_adjudication_context_snapshot(
                    turn_execution=execution,
                    persistent_memory_snapshot=persistent_memory,
                    story_memory_snapshot=story_memory,
                )
            ),
        )
