from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from llm_service.manager import LLMManager
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.agent.agent_types import StreamEventKind
from rpg_core.tests.integration.conftest import (
    _create_integration_session,
    _shutdown_agent,
)

pytestmark = [pytest.mark.integration, pytest.mark.live_llm]


@pytest_asyncio.fixture
async def live_agent(
    request,
    integration_settings,
    integration_workspace,
    integration_data_gateway,
):
    if not integration_settings.resolve_openai_api_key():
        pytest.skip("the active test profile has no real main-agent API key")
    session_id = f"live_{request.node.name[-24:]}".replace("-", "_")
    _create_integration_session(integration_data_gateway, integration_workspace, session_id)
    agent = RPGGameAgent(session_id=session_id)
    await agent._ensure_initialized()
    try:
        yield agent
    finally:
        await _shutdown_agent(agent)
        LLMManager.reset()


@pytest.mark.asyncio
async def test_live_non_stream_provider_smoke(live_agent):
    reply = await asyncio.wait_for(
        live_agent.send("Reply with exactly: live non-stream ok"),
        timeout=120,
    )

    assert reply.text.strip()
    assert reply.stats is not None
    assert reply.stats.total_tokens > 0


@pytest.mark.asyncio
async def test_live_stream_provider_smoke(live_agent):
    events = []
    async with asyncio.timeout(120):
        async for event in live_agent.send_stream("Reply with exactly: live stream ok"):
            events.append(event)

    assert events
    assert events[-1].kind == StreamEventKind.DONE
    assert events[-1].content.strip()
    assert events[-1].usage is not None
    assert events[-1].usage.total_tokens > 0
