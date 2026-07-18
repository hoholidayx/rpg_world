"""Command and guard handling before a normal turn allocates resources."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.turn.models import TurnBypass, TurnRequest

if TYPE_CHECKING:
    from rpg_core.agent.command.dispatcher import CommandDispatcher

_TAG = "[TurnPreprocessor]"


class TurnPreprocessor:
    """Resolve non-LLM replies before snapshots, gates, and transactions."""

    def __init__(
        self,
        *,
        session_id: str,
        command_dispatcher: "CommandDispatcher | None",
        player_character_guard: Callable[[], str],
    ) -> None:
        self._session_id = session_id
        self._command_dispatcher = command_dispatcher
        self._player_character_guard = player_character_guard

    async def resolve(self, request: TurnRequest) -> TurnBypass | None:
        dispatcher = self._command_dispatcher
        if dispatcher is not None and dispatcher.is_command(request.text):
            result = await dispatcher.dispatch(request.text)
            if result.handled:
                return TurnBypass(
                    text=result.reply,
                    reason="command",
                    active_session=result.active_session,
                )

        role_guard_reply = self._player_character_guard()
        if not role_guard_reply:
            return None
        logger.info(
            _TAG + " blocked turn because player character is invalid: session_id={}",
            self._session_id,
        )
        return TurnBypass(text=role_guard_reply, reason="player_character_guard")
