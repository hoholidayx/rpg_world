"""Fixed, typed hooks for the invariant Agent turn stages."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.resources import AgentContextResources
from rpg_core.agent.sub_agents import (
    StatusSubAgentPreflightOutcome,
    StatusSubAgentResult,
)
from rpg_core.agent.transaction import SCENE_TOOL_NAMES
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_TOOL_NAME
from rpg_core.status.context import render_status_tables_context
from rpg_core.status.tools import STATUS_TABLE_SET_VALUES_TOOL_NAME

if TYPE_CHECKING:
    from rpg_core.agent.agent_types import TurnStats
    from rpg_core.agent.lifecycle import AgentRuntimeLifecycle
    from rpg_core.agent.loop import ToolCallRecord
    from rpg_core.agent.sub_agents import StatusSubAgent
    from rpg_core.agent.tool_service import AgentToolService
    from rpg_core.agent.transaction import TurnScratch
    from rpg_core.rp_modules import RPModuleTurnRuntime
    from rpg_core.scene import SceneTracker
    from rpg_core.session import SessionManager
    from rpg_core.status.manager import StatusManager

_TAG = "[TurnHooks]"


class StatusPreflightHook:
    """Critical preflight hook with scratch checkpoint/restore semantics."""

    def __init__(
        self,
        *,
        status_sub_agent: Callable[[], "StatusSubAgent | None"],
        tool_service: "AgentToolService",
    ) -> None:
        self._status_sub_agent = status_sub_agent
        self._tool_service = tool_service

    async def run(
        self,
        *,
        turn_scratch: "TurnScratch",
        user_input: str,
        turn_stats: "TurnStats",
        rp_module_runtime: "RPModuleTurnRuntime | None" = None,
    ) -> StatusSubAgentResult | None:
        sub_agent = self._status_sub_agent()
        if sub_agent is None:
            return None
        tools = [
            *self._tool_service.narrative_outcome_tools(
                user_input,
                rp_module_runtime,
            ),
            *self._tool_service.state_tools(
                turn_scratch.scene_tracker,
                turn_scratch.status_manager,
            ),
        ]
        if not tools:
            return None

        def create_checkpoint() -> object:
            scene_time = (
                turn_scratch.scene_tracker.get_time_state()
                if turn_scratch.scene_tracker is not None
                else None
            )
            return turn_scratch.status_scratch.create_checkpoint(), scene_time

        def restore_checkpoint(checkpoint: object) -> None:
            status_checkpoint, scene_time = checkpoint  # type: ignore[misc]
            turn_scratch.status_scratch.restore_checkpoint(status_checkpoint)
            if turn_scratch.scene_tracker is not None and scene_time is not None:
                turn_scratch.scene_tracker.set_time_state(scene_time)

        with sub_agent.use_turn_tools(
            tools,
            mutation_probe=lambda: turn_scratch.status_scratch.change_token,
            create_checkpoint=create_checkpoint,
            restore_checkpoint=restore_checkpoint,
            outcome_preflight_enabled=any(
                tool.name == NARRATIVE_OUTCOME_TOOL_NAME for tool in tools
            ),
        ):
            result = await sub_agent.update(
                history=turn_scratch.base_history,
                state_context=self._state_context(
                    turn_scratch.scene_tracker,
                    turn_scratch.status_manager,
                ),
                user_input=user_input,
                turn_stats=turn_stats,
            )
        if result.updated:
            logger.info(
                _TAG + " StatusSubAgent updated state via {}",
                [record.tool_name for record in result.records if record.changed],
            )
        return result

    @staticmethod
    def outcome_state(
        turn_scratch: "TurnScratch",
        result: StatusSubAgentResult | None,
    ) -> StatusSubAgentPreflightOutcome:
        if turn_scratch.narrative_outcome is not None:
            return StatusSubAgentPreflightOutcome.STAGED
        if result is not None and (result.failed or result.outcome_requested):
            return StatusSubAgentPreflightOutcome.FALLBACK
        return StatusSubAgentPreflightOutcome.NONE

    @staticmethod
    def _state_context(
        scene_tracker: "SceneTracker | None",
        status_manager: "StatusManager | None",
    ) -> str:
        sections: list[str] = []
        if scene_tracker is not None:
            sections.append(scene_tracker.get_context())
        if status_manager is not None:
            try:
                status_context = render_status_tables_context(
                    status_manager.list_context_tables()
                )
            except Exception as exc:
                logger.warning(
                    _TAG + " failed to render status context for sub-agent: {}",
                    exc,
                )
                status_context = ""
            if status_context:
                sections.append(status_context)
        return "\n\n".join(sections)


class MemoryRecallHook:
    """Warning-only memory recall before the main Context is built."""

    def __init__(
        self,
        resources: Callable[[], AgentContextResources],
    ) -> None:
        self._resources = resources

    def run(self, user_input: str) -> None:
        manager = self._resources().memory_manager
        if manager is None:
            return
        try:
            manager.recall(user_input)
        except Exception as exc:
            logger.opt(exception=exc).warning(_TAG + " memory recall failed")


class PostCommitHooks:
    """Warning-isolated side effects that never roll back a committed turn."""

    def __init__(
        self,
        *,
        lifecycle: "AgentRuntimeLifecycle",
        session_manager: "SessionManager",
    ) -> None:
        self._lifecycle = lifecycle
        self._session_manager = session_manager

    async def run(self) -> None:
        memory_sub_agent = self._lifecycle.memory_sub_agent
        if memory_sub_agent is not None:
            try:
                await memory_sub_agent.maybe_auto_extract(self._session_manager)
            except Exception as exc:
                logger.opt(exception=exc).warning(
                    _TAG + " post-commit story memory extraction failed"
                )

        compressor = self._lifecycle.compressor
        if compressor is not None:
            try:
                result = await compressor.maybe_compress(self._session_manager)
                if result.triggered:
                    logger.info(
                        _TAG + " auto-compressed: {} turns, {} batches",
                        result.user_rounds_compressed,
                        len(result.batch_files or []),
                    )
            except Exception as exc:
                logger.opt(exception=exc).warning(
                    _TAG + " post-commit auto-compress failed"
                )


class TurnDiagnostics:
    """Extract and log turn tool/preflight diagnostics outside the facade."""

    @staticmethod
    def tool_names(records: list["ToolCallRecord"]) -> list[str]:
        names: list[str] = []
        for record in records:
            tool_calls = record.assistant_message.get("tool_calls", [])
            if not isinstance(tool_calls, list):
                continue
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function")
                if not isinstance(function, dict):
                    continue
                name = str(function.get("name", "") or "")
                if name:
                    names.append(name)
        return names

    @staticmethod
    def log_preflight(
        *,
        turn_scratch: "TurnScratch",
        preflight_outcome: StatusSubAgentPreflightOutcome,
        state_prewrites_skipped: int,
        main_tool_names: list[str],
    ) -> None:
        effective = preflight_outcome
        if (
            effective is StatusSubAgentPreflightOutcome.NONE
            and turn_scratch.narrative_outcome is not None
        ):
            effective = StatusSubAgentPreflightOutcome.FALLBACK
        state_tool_names = SCENE_TOOL_NAMES | {STATUS_TABLE_SET_VALUES_TOOL_NAME}
        main_state_corrections = sum(
            name in state_tool_names for name in main_tool_names
        )
        outcome_reused_by_main = (
            preflight_outcome is StatusSubAgentPreflightOutcome.STAGED
            and NARRATIVE_OUTCOME_TOOL_NAME in main_tool_names
        )
        logger.info(
            _TAG
            + " preflightOutcome={} statePrewritesSkipped={} "
            "mainStateCorrections={} outcomeReusedByMain={}",
            effective.value,
            int(state_prewrites_skipped),
            int(main_state_corrections),
            outcome_reused_by_main,
        )
