"""Protocol adapters around the shared turn orchestrator."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from rpg_core.agent.mailbox.models import _StreamSentinel
from rpg_core.agent.protocol import AgentStreamEvent, StreamEventKind
from rpg_core.agent.telemetry import TurnStats
from rpg_core.agent.turn.models import TurnBypass, TurnRequest
from rpg_core.agent.turn.preprocessor import TurnPreprocessor
from rpg_core.agent.turn.runner import AgentReply
from rpg_core.agent.turn.resolver import PlayerCharacterRequiredError
from rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_core.agent.command.dispatcher import CommandDispatcher
    from rpg_core.agent.turn.runner import ToolCallRecord
    from rpg_core.agent.turn.orchestrator import TurnOrchestrator


class AgentTurnService:
    """Handle command/role bypasses and adapt turn results to public protocols."""

    def __init__(
        self,
        *,
        session_id: Callable[[], str],
        model: Callable[[], str | None],
        command_dispatcher: "CommandDispatcher",
        player_character_guard: Callable[[], str],
        orchestrator: "TurnOrchestrator",
        stream_error_event: Callable[[BaseException], AgentStreamEvent],
    ) -> None:
        self._session_id = session_id
        self._model = model
        self._command_dispatcher = command_dispatcher
        self._player_character_guard = player_character_guard
        self._orchestrator = orchestrator
        self._stream_error_event = stream_error_event

    @property
    def last_tool_records(self) -> list["ToolCallRecord"] | None:
        return self._orchestrator.last_tool_records

    async def execute_sync(self, request: TurnRequest) -> AgentReply:
        bypass = await self._resolve_bypass(request)
        if bypass is not None:
            return self._reply_for_bypass(bypass)
        try:
            result = await self._orchestrator.execute_sync(request)
        except PlayerCharacterRequiredError as exc:
            return self._reply_for_bypass(
                TurnBypass(text=exc.reply, reason="player_character_guard")
            )
        return AgentReply(
            text=result.text,
            tool_records=(
                (result.tool_records or None)
                if settings.include_tool_records
                else None
            ),
            status_sub_agent_records=result.status_sub_agent_records,
            stats=result.stats,
            committed_turn_id=result.committed_turn_id,
        )

    async def execute_stream(
        self,
        request: TurnRequest,
        event_queue: asyncio.Queue,
    ) -> int | None:
        bypass = await self._resolve_bypass(request)
        if bypass is not None:
            await self._emit_bypass(event_queue, bypass)
            return None

        async def emit_error(error: BaseException) -> None:
            await event_queue.put(self._stream_error_event(error))
            await event_queue.put(_StreamSentinel())

        async def emit_end() -> None:
            await event_queue.put(_StreamSentinel())

        try:
            result = await self._orchestrator.execute_stream(
                request,
                emit_event=event_queue.put,
                emit_error=emit_error,
                emit_end=emit_end,
            )
            return result.committed_turn_id if result is not None else None
        except PlayerCharacterRequiredError as exc:
            await self._emit_bypass(
                event_queue,
                TurnBypass(text=exc.reply, reason="player_character_guard"),
            )
            return None

    async def _resolve_bypass(self, request: TurnRequest) -> TurnBypass | None:
        return await TurnPreprocessor(
            session_id=self._session_id(),
            command_dispatcher=self._command_dispatcher,
            player_character_guard=self._player_character_guard,
        ).resolve(request)

    @staticmethod
    def _reply_for_bypass(bypass: TurnBypass) -> AgentReply:
        stats = TurnStats(started_at=time.monotonic())
        stats.finished_at = time.monotonic()
        return AgentReply(text=bypass.text, stats=stats)

    async def _emit_bypass(
        self,
        event_queue: asyncio.Queue,
        bypass: TurnBypass,
    ) -> None:
        if bypass.text:
            await event_queue.put(
                AgentStreamEvent(
                    kind=StreamEventKind.TEXT,
                    content=bypass.text,
                    model=self._model(),
                )
            )
        await event_queue.put(
            AgentStreamEvent(
                kind=StreamEventKind.DONE,
                content=bypass.text,
                model=self._model(),
            )
        )
        await event_queue.put(_StreamSentinel())
