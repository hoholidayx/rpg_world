"""Prepare context, tools, and schemas against a turn scratch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.turn.models import PreparedTurn
from rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_core.agent.context_service import AgentContextService
    from rpg_core.agent.tool_service import AgentToolService
    from rpg_core.agent.turn.hooks import MemoryRecallHook
    from rpg_core.agent.turn.runtime import TurnRuntime
    from rpg_core.context.rpg_context import Message

_TAG = "[TurnPreparation]"


class TurnPreparation:
    """Build all main-Agent inputs from one immutable plan and COW scratch."""

    def __init__(
        self,
        *,
        context_service: "AgentContextService",
        tool_service: "AgentToolService",
        memory_recall: "MemoryRecallHook",
    ) -> None:
        self._context_service = context_service
        self._tool_service = tool_service
        self._memory_recall = memory_recall

    def build(self, runtime: "TurnRuntime") -> PreparedTurn:
        request = runtime.plan.request
        scratch = runtime.scratch
        scene_ctx = scratch.scene_tracker.get_context() if scratch.scene_tracker else None
        stored_input = self._context_service.compose_stored_user_input(
            scene_ctx,
            request.text,
        )
        current_user_message = runtime.transaction.stage_user_message(stored_input)

        self._memory_recall.run(request.text)

        messages = self._context_service.build_transformed_context(
            current_user_message=current_user_message,
            status_manager=scratch.status_manager,
            scene_tracker=scratch.scene_tracker,
            user_input=request.text,
            rp_module_runtime=runtime.rp_module_runtime,
            turn_execution=runtime.plan.execution,
        )
        self._log_context_shape(messages)
        tool_registry = self._tool_service.registry_for_turn(
            scratch.scene_tracker,
            scratch.status_manager,
            rp_module_runtime=runtime.rp_module_runtime,
            turn_execution=runtime.plan.execution,
        )
        schemas = self._tool_service.main_schemas(
            tool_registry,
            rp_module_runtime=runtime.rp_module_runtime,
        )
        return PreparedTurn(
            messages=messages,
            tool_registry=tool_registry,
            schemas=schemas,
        )

    @staticmethod
    def _log_context_shape(messages: list["Message"]) -> None:
        if not settings.verbose_logging:
            return
        sys_msgs = sum(1 for message in messages if message.is_system())
        user_msgs = sum(1 for message in messages if message.is_user())
        assistant_msgs = sum(1 for message in messages if message.is_assistant())
        total_chars = sum(len(message.content) for message in messages)
        logger.debug(
            _TAG + " context messages: {} total (sys={}, user={}, asst={}) chars={}",
            len(messages),
            sys_msgs,
            user_msgs,
            assistant_msgs,
            total_chars,
        )
