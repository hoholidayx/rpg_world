from __future__ import annotations

import asyncio

import pytest

from rpg_core.agent.command import CommandResult
from rpg_core.agent.protocol import StreamEventKind
from rpg_core.agent.turn.models import TurnRequest
from rpg_core.agent.turn.resolver import PlayerCharacterRequiredError
from rpg_core.agent.turn.service import AgentTurnService


class _Commands:
    @staticmethod
    def is_command(_text: str) -> bool:
        return False


class _RoleLostOrchestrator:
    last_tool_records = None

    @staticmethod
    async def execute_sync(_request):  # noqa: ANN001, ANN205
        raise PlayerCharacterRequiredError("请选择角色")

    @staticmethod
    async def execute_stream(_request, **_kwargs):  # noqa: ANN001, ANN205
        raise PlayerCharacterRequiredError("请选择角色")


class _SwitchCommands:
    @staticmethod
    def is_command(_text: str) -> bool:
        return True

    @staticmethod
    async def dispatch(_text: str) -> CommandResult:
        return CommandResult(
            reply="[已切换到会话: s2]",
            handled=True,
            active_session="s2",
        )


def _service() -> AgentTurnService:
    return AgentTurnService(
        session_id=lambda: "s1",
        model=lambda: "model",
        command_dispatcher=_Commands(),
        player_character_guard=lambda: "",
        orchestrator=_RoleLostOrchestrator(),
        stream_error_event=lambda error: error,
    )


@pytest.mark.asyncio
async def test_role_lost_after_preprocessor_returns_sync_bind_prompt() -> None:
    reply = await _service().execute_sync(TurnRequest.create("行动"))

    assert reply.text == "请选择角色"
    assert reply.committed_turn_id is None


@pytest.mark.asyncio
async def test_role_lost_after_preprocessor_returns_stream_bind_prompt() -> None:
    queue: asyncio.Queue = asyncio.Queue()

    await _service().execute_stream(TurnRequest.create("行动"), queue)

    text_event = await queue.get()
    done_event = await queue.get()
    await queue.get()
    assert text_event.kind == StreamEventKind.TEXT
    assert text_event.content == "请选择角色"
    assert done_event.kind == StreamEventKind.DONE
    assert done_event.content == "请选择角色"


@pytest.mark.asyncio
async def test_command_locator_propagates_through_sync_bypass() -> None:
    service = AgentTurnService(
        session_id=lambda: "s1",
        model=lambda: "model",
        command_dispatcher=_SwitchCommands(),
        player_character_guard=lambda: "",
        orchestrator=_RoleLostOrchestrator(),
        stream_error_event=lambda error: error,
    )

    reply = await service.execute_sync(TurnRequest.create("/session_switch s2"))

    assert reply.text == "[已切换到会话: s2]"
    assert reply.active_session == "s2"


@pytest.mark.asyncio
async def test_command_locator_is_only_attached_to_stream_done() -> None:
    service = AgentTurnService(
        session_id=lambda: "s1",
        model=lambda: "model",
        command_dispatcher=_SwitchCommands(),
        player_character_guard=lambda: "",
        orchestrator=_RoleLostOrchestrator(),
        stream_error_event=lambda error: error,
    )
    queue: asyncio.Queue = asyncio.Queue()

    await service.execute_stream(TurnRequest.create("/session_switch s2"), queue)

    text_event = await queue.get()
    done_event = await queue.get()
    await queue.get()
    assert text_event.kind == StreamEventKind.TEXT
    assert text_event.active_session is None
    assert done_event.kind == StreamEventKind.DONE
    assert done_event.active_session == "s2"
