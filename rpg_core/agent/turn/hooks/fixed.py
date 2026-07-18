"""Fixed, typed hooks for the invariant Agent turn stages."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.runtime.resources import AgentContextResources
from rpg_core.agent.sub_agents.status.models import (
    OutcomeDecision,
    StatusSubAgentPreflightOutcome,
    StatusSubAgentResult,
)
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_TOOL_NAME
from rpg_core.scene import SCENE_TOOL_NAMES
from rpg_core.status.context import render_status_tables_context
from rpg_core.status.tools import STATUS_TABLE_SET_VALUES_TOOL_NAME

if TYPE_CHECKING:
    from rpg_core.agent.runtime.lifecycle import AgentRuntimeLifecycle
    from rpg_core.agent.runtime.tools import AgentToolService
    from rpg_core.agent.sub_agents.status.agent import StatusSubAgent
    from rpg_core.agent.telemetry import TurnStats
    from rpg_core.agent.turn.models import TurnPlayerCharacterSnapshot
    from rpg_core.agent.turn.runner import ToolCallRecord
    from rpg_core.agent.turn.transaction import TurnScratch
    from rpg_core.rp_modules.runtime import RPModuleTurnRuntime
    from rpg_core.scene import SceneTracker
    from rpg_core.session import SessionManager
    from rpg_core.status.manager import StatusManager

_TAG = "[TurnHooks]"


class StatusPreflightHook:
    """Critical preflight hook with target-scoped scratch rollback callbacks."""

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
        player_character: "TurnPlayerCharacterSnapshot | None" = None,
    ) -> StatusSubAgentResult | None:
        sub_agent = self._status_sub_agent()
        if sub_agent is None:
            return None
        state_tool_set = self._tool_service.state_tools(
            turn_scratch.scene_tracker,
            turn_scratch.status_manager,
        )
        tools = [
            *self._tool_service.narrative_outcome_tools(
                user_input,
                rp_module_runtime,
            ),
            *state_tool_set,
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
            context_tables = (
                turn_scratch.status_manager.list_context_tables()
                if turn_scratch.status_manager is not None
                else []
            )
            state_context = self._state_context(
                turn_scratch.scene_tracker,
                turn_scratch.status_manager,
                context_tables=context_tables,
            )
            scene_context = (
                turn_scratch.scene_tracker.get_context()
                if turn_scratch.scene_tracker is not None
                else ""
            )
            result = await sub_agent.run_preflight(
                history=turn_scratch.base_history,
                state_context=state_context,
                scene_context=scene_context,
                context_tables=context_tables,
                user_input=user_input,
                turn_stats=turn_stats,
                player_character=player_character,
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
        if result is not None:
            if result.outcome_decision is OutcomeDecision.FALLBACK:
                return StatusSubAgentPreflightOutcome.FALLBACK
            if result.failed and result.route is None:
                return StatusSubAgentPreflightOutcome.FALLBACK
        return StatusSubAgentPreflightOutcome.NONE

    @staticmethod
    def _state_context(
        scene_tracker: "SceneTracker | None",
        status_manager: "StatusManager | None",
        *,
        context_tables: list[dict[str, object]] | None = None,
    ) -> str:
        sections: list[str] = []
        if scene_tracker is not None:
            sections.append(scene_tracker.get_context())
        if status_manager is not None:
            try:
                status_context = render_status_tables_context(
                    context_tables
                    if context_tables is not None
                    else status_manager.list_context_tables()
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
        session_manager: "SessionManager",
    ) -> None:
        self._resources = resources
        self._session_manager = session_manager

    async def run(
        self,
        user_input: str,
        *,
        player_character: "TurnPlayerCharacterSnapshot | None" = None,
        scene_tracker: "SceneTracker | None" = None,
    ) -> None:
        manager = self._resources().memory_manager
        if manager is None:
            return
        try:
            from rp_memory.recall_query import RecallQueryContext

            scene = scene_tracker.get_recall_context() if scene_tracker is not None else {}
            await manager.recall(
                RecallQueryContext(
                    current_input=user_input,
                    recent_turns=self._recent_ic_gm_turns(),
                    player_character=player_character.name if player_character is not None else "",
                    scene_time=str(scene.get("time", "")),
                    scene_location=str(scene.get("location", "")),
                )
            )
        except Exception as exc:
            logger.opt(exception=exc).warning(_TAG + " memory recall failed")

    def _recent_ic_gm_turns(self) -> tuple[str, ...]:
        from rpg_core.agent.turn.models import TurnMode

        messages = [
            message
            for message in self._session_manager.history
            if not message.is_system() and not message.is_tool()
        ]
        groups = []
        for group in self._session_manager.iter_turn_groups(messages):
            modes = {str(message.mode or TurnMode.IC.value).lower() for message in group}
            if modes and modes.issubset({TurnMode.IC.value, TurnMode.GM.value}):
                groups.append(group)
        rendered: list[str] = []
        for index, group in enumerate(groups[-2:], start=1):
            lines = [f"Turn {index}:"]
            for message in group:
                label = "Player" if message.is_user() else "GM"
                content = " ".join(str(message.content or "").split())
                if content:
                    lines.append(f"{label}: {content[:500]}")
            if len(lines) > 1:
                rendered.append("\n".join(lines))
        return tuple(rendered)


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
                if result.failed:
                    logger.warning(
                        _TAG + " post-commit auto-compress failed: code={} message={}",
                        result.error_code,
                        result.error_message,
                    )
                elif result.triggered:
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
        outcome_repeat_requested_by_main = (
            preflight_outcome is StatusSubAgentPreflightOutcome.STAGED
            and NARRATIVE_OUTCOME_TOOL_NAME in main_tool_names
        )
        logger.info(
            _TAG
            + " preflightOutcome={} statePrewritesSkipped={} "
            "mainStateCorrections={} outcomeRepeatRequestedByMain={}",
            effective.value,
            int(state_prewrites_skipped),
            int(main_state_corrections),
            outcome_repeat_requested_by_main,
        )
