from __future__ import annotations

import asyncio

import pytest

from rpg_core.agent.agent_types import StreamEventKind
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
