"""Prepare context, tools, and schemas against a turn scratch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.turn.models import PreparedTurn
from rpg_core.context.fingerprint import (
    build_request_fingerprint,
    request_fingerprint_log_values,
)
from rpg_core.context.rpg_context import Message
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

    async def build(self, runtime: "TurnRuntime") -> PreparedTurn:
        request = runtime.plan.request
        scratch = runtime.scratch
        scene_tracker = scratch.scene_tracker
        llm_scene_context = scene_tracker.get_context() if scene_tracker else None
        persisted_scene_context = (
            scene_tracker.get_snapshot_context() if scene_tracker else None
        )
        stored_input = self._context_service.compose_scene_user_input(
            persisted_scene_context,
            request.text,
        )
        stored_user_message = runtime.transaction.stage_user_message(stored_input)
        # The prompt guidance belongs to the LLM request, not durable history.
        llm_input = (
            stored_input
            if llm_scene_context == persisted_scene_context
            else self._context_service.compose_scene_user_input(
                llm_scene_context,
                request.text,
            )
        )
        current_user_message = Message(
            role=stored_user_message.role,
            content=llm_input,
            mode=stored_user_message.mode,
            turn_id=stored_user_message.turn_id,
            seq_in_turn=stored_user_message.seq_in_turn,
        )

        await self._memory_recall.run(
            request.text,
            player_character=runtime.plan.execution.player_character,
            scene_tracker=scratch.scene_tracker,
        )

        messages = self._context_service.build_transformed_context(
            current_user_message=current_user_message,
            status_manager=scratch.status_manager,
            scene_tracker=scratch.scene_tracker,
            user_input=request.text,
            rp_module_runtime=runtime.rp_module_runtime,
            turn_execution=runtime.plan.execution,
        )
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
        self._log_request_fingerprint(messages, schemas)
        return PreparedTurn(
            messages=messages,
            tool_registry=tool_registry,
            schemas=schemas,
        )

    @staticmethod
    def _log_request_fingerprint(
        messages: list["Message"],
        schemas: list[dict[str, object]] | None,
    ) -> None:
        if not settings.verbose_logging:
            return
        fingerprint = build_request_fingerprint(messages, schemas)
        logger.info(
            _TAG + " main LLM request fingerprint: source=main_initial "
            "contextHash={} contextChars={} systemHash={} systemChars={} "
            "toolsHash={} toolsChars={} messages={} roles={} tools={} "
            "messageShape={}",
            *request_fingerprint_log_values(fingerprint),
        )
