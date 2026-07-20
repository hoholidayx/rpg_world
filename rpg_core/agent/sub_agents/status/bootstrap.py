"""Outcome-free state bootstrap for a history-derived session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_data.model import status as models
from rpg_core.agent.telemetry import TurnStats
from rpg_core.agent.sub_agents.status.models import StatusBootstrapResult
from rpg_core.agent.turn.transaction.status_scratch import (
    ScratchStatusManager,
    StatusDocumentScratch,
)
from rpg_core.agent.turn.models import TurnMode
from rpg_core.scene import SceneTracker
from rpg_core.session.manager import SessionManager
from rpg_core.settings import settings
from rpg_core.status.tools import StatusTableSetValuesTool, StatusWritePolicy

if TYPE_CHECKING:
    from rpg_core.agent.sub_agents.status.agent import StatusSubAgent
    from rpg_core.agent.turn.models import TurnPlayerCharacterSnapshot
    from rpg_core.context.models import Message
    from rpg_core.status.manager import StatusManager


def select_status_bootstrap_history(
    history: list["Message"],
    *,
    boundary_turn_id: int,
    history_rounds: int | None = None,
) -> list["Message"]:
    """Select the latest complete IC/GM turns at or before a branch boundary."""
    if boundary_turn_id <= 0:
        raise ValueError("boundary_turn_id must be positive")
    rounds = settings.status_history_rounds if history_rounds is None else int(history_rounds)
    if rounds <= 0:
        raise ValueError("history_rounds must be positive")

    selected_groups: list[list[Message]] = []
    bounded = [message for message in history if 0 < message.turn_id <= boundary_turn_id]
    for group in SessionManager.iter_turn_groups(bounded):
        if not group:
            continue
        turn_id = group[0].turn_id
        if turn_id <= 0 or any(message.turn_id != turn_id for message in group):
            continue
        if [message.seq_in_turn for message in group] != list(
            range(1, len(group) + 1)
        ):
            continue
        conversation = [
            message
            for message in group
            if not message.is_system() and not message.is_tool()
        ]
        modes = {str(message.mode or TurnMode.IC.value).strip().lower() for message in conversation}
        if not modes or not modes.issubset({TurnMode.IC.value, TurnMode.GM.value}):
            continue
        if not any(message.is_user() for message in conversation):
            continue
        if not any(message.is_assistant() for message in conversation):
            continue
        if not conversation[-1].is_assistant():
            continue
        selected_groups.append(conversation)
    return [message for group in selected_groups[-rounds:] for message in group]


class StatusBootstrapCoordinator:
    """Run all bootstrap LLM calls in scratch, then publish once atomically."""

    def __init__(self, status_sub_agent: "StatusSubAgent") -> None:
        self._status_sub_agent = status_sub_agent

    async def run(
        self,
        *,
        history: list["Message"],
        boundary_turn_id: int,
        status_manager: "StatusManager",
        scene_tracker: SceneTracker | None,
        turn_stats: TurnStats | None = None,
        player_character: "TurnPlayerCharacterSnapshot | None" = None,
    ) -> StatusBootstrapResult:
        rounds = settings.status_history_rounds
        selected_history = select_status_bootstrap_history(
            history,
            boundary_turn_id=boundary_turn_id,
            history_rounds=rounds,
        )
        scratch = StatusDocumentScratch(status_manager)
        scratch_manager = ScratchStatusManager(status_manager, scratch)
        scratch_scene = self._scratch_scene(scene_tracker, scratch_manager)
        tools = []
        if scratch_scene is not None:
            tools.extend(scratch_scene.get_tools())
        tools.append(StatusTableSetValuesTool(
            scratch_manager,
            write_policy=StatusWritePolicy(
                allowed_frequencies=frozenset({
                    models.STATUS_UPDATE_FREQUENCY_REALTIME,
                    models.STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
                    models.STATUS_UPDATE_FREQUENCY_DEFERRED,
                })
            ),
        ))

        def create_checkpoint() -> object:
            return (
                scratch.create_checkpoint(),
                scratch_scene.get_time_state() if scratch_scene is not None else None,
            )

        def restore_checkpoint(checkpoint: object) -> None:
            status_checkpoint, scene_time = checkpoint  # type: ignore[misc]
            scratch.restore_checkpoint(status_checkpoint)
            if scratch_scene is not None and scene_time is not None:
                scratch_scene.set_time_state(scene_time)

        with self._status_sub_agent.use_turn_tools(
            tools,
            mutation_probe=lambda: scratch.change_token,
            create_checkpoint=create_checkpoint,
            restore_checkpoint=restore_checkpoint,
            outcome_preflight_enabled=False,
        ):
            context_tables = scratch_manager.list_context_tables()
            result = await self._status_sub_agent.bootstrap_state(
                history=selected_history,
                scene_context=(
                    scratch_scene.get_context() if scratch_scene is not None else ""
                ),
                context_tables=context_tables,
                max_history_rounds=rounds,
                turn_stats=turn_stats,
                player_character=player_character,
            )
        if result.failed:
            return result
        status_manager.commit_bootstrap_state(
            scratch.staged_changes,
            deferred_progress=result.deferred_progress,
            boundary_turn_id=boundary_turn_id,
        )
        return result

    @staticmethod
    def _scratch_scene(
        scene_tracker: SceneTracker | None,
        status_manager: ScratchStatusManager,
    ) -> SceneTracker | None:
        if scene_tracker is None:
            return None
        scratch_scene = SceneTracker(
            allow_runtime_key_changes=scene_tracker.allow_runtime_key_changes
        )
        scratch_scene.set_time_state(scene_tracker.get_time_state())
        scratch_scene.bind_status_manager(status_manager)
        scratch_scene.load_from_status_table()
        return scratch_scene
