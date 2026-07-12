from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from rpg_core.agent.agent import RPGGameAgent
from rpg_core.agent.loop import AgentReply
from rpg_core.agent.turn import TurnMode


class _Lifecycle:
    def __init__(self) -> None:
        self.session_id = "s_facade"
        self.session_manager = object()
        self.initialize_calls = 0

    async def initialize(self, *, tool_service, mailbox) -> None:  # noqa: ANN001
        assert tool_service == "tools"
        assert mailbox is not None
        self.initialize_calls += 1


class _Mailbox:
    def __init__(self) -> None:
        self.requests = []

    async def send(self, request):  # noqa: ANN001, ANN201
        self.requests.append(request)
        return AgentReply(text="ok")


def _facade() -> RPGGameAgent:
    agent = object.__new__(RPGGameAgent)
    agent._lifecycle = _Lifecycle()
    agent._tool_service = "tools"
    agent._mailbox = _Mailbox()
    return agent


@pytest.mark.asyncio
async def test_facade_send_initializes_and_normalizes_turn_request() -> None:
    agent = _facade()

    reply = await agent.send(
        "解释规则",
        mode=" OOC ",
        narrative_style_id=7,
    )

    assert reply.text == "ok"
    assert agent._lifecycle.initialize_calls == 1
    request = agent._mailbox.requests[0]
    assert request.text == "解释规则"
    assert request.mode is TurnMode.OOC
    assert request.narrative_style_id == 7


def test_facade_exposes_stable_read_only_session_interfaces() -> None:
    agent = _facade()

    assert agent.session_id == "s_facade"
    assert agent.session_manager is agent._lifecycle.session_manager


def test_agent_module_is_a_small_composition_facade() -> None:
    source_path = Path(__file__).parents[1] / "agent" / "agent.py"
    source = source_path.read_text(encoding="utf-8")

    assert len(source.splitlines()) <= 500
    assert "class TurnHost" not in source
    assert "TurnPreparationHost" not in source
    assert "_rpg_ctx" not in source
    assert "async def _send_impl" not in source
    assert "async def _queue_consumer" not in source
