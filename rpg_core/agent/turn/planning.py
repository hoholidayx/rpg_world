"""Resolve all immutable selections before allocating turn scratch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.agent.turn.models import TurnExecutionPlan, TurnRequest

if TYPE_CHECKING:
    from rpg_core.agent.context_service import AgentContextService
    from rpg_core.agent.lifecycle import AgentRuntimeLifecycle
    from rpg_core.agent.model_runtime import MainModelRuntime


class TurnPlanResolver:
    """Combine mode/style, main-model, and RP-module snapshots."""

    def __init__(
        self,
        *,
        lifecycle: "AgentRuntimeLifecycle",
        context_service: "AgentContextService",
        model_runtime: "MainModelRuntime",
    ) -> None:
        self._lifecycle = lifecycle
        self._context_service = context_service
        self._model_runtime = model_runtime

    def resolve(self, request: TurnRequest) -> TurnExecutionPlan:
        return TurnExecutionPlan(
            execution=self._context_service.resolve_turn_execution(
                request,
                require_player_character=True,
            ),
            main_llm=self._model_runtime.resolve(self._lifecycle.session_id),
            rp_modules=self._context_service.resolve_rp_module_snapshot(),
        )
