from __future__ import annotations

import random

import pytest

from llm_service.types import LLMResponse, ProviderChunk
from rpg_core.agent.agent_types import StreamEventKind
from rpg_core.agent.loop import run_chat_loop, run_chat_loop_stream
from rpg_core.tooling.registry import ToolRegistry
from rpg_core.context.rpg_context import Message, Role
from rpg_core.rp_modules.dice.tools import DiceCheckDCTool, DiceRoller
from rpg_core.settings import DiceModuleSettings


class _MissingToolPayloadProvider:
    def get_default_model(self) -> str:
        return "missing-tool-payload"

    async def chat(self, messages, tools=None):  # noqa: ANN001
        del messages, tools
        return LLMResponse(
            content="",
            tool_calls=None,
            finish_reason="tool_calls",
            model=self.get_default_model(),
        )

    async def chat_stream(self, messages, tools=None):  # noqa: ANN001
        del messages, tools
        yield ProviderChunk(
            finish_reason="tool_calls",
            model=self.get_default_model(),
        )


class _DiceThenNarrateStreamProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_default_model(self) -> str:
        return "dice-stream"

    async def chat(self, messages, tools=None):  # noqa: ANN001
        del messages, tools
        raise AssertionError("stream test must not call chat")

    async def chat_stream(self, messages, tools=None):  # noqa: ANN001
        del tools
        self.calls += 1
        if self.calls == 1:
            assert not any(message.get("role") == "tool" for message in messages)
            yield ProviderChunk(
                tool_calls=[{
                    "id": "call_dice",
                    "function": {
                        "name": "rp_dice_check_dc",
                        "arguments": '{"reason":"搜索线索"}',
                    },
                }],
                finish_reason="tool_calls",
                model=self.get_default_model(),
            )
            return

        assert any(
            message.get("role") == "tool"
            and "expression=1d20" in str(message.get("content"))
            and "dc=13" in str(message.get("content"))
            for message in messages
        )
        yield ProviderChunk(content="你在祭坛附近发现了一道新划痕。")
        yield ProviderChunk(finish_reason="stop", model=self.get_default_model())


@pytest.mark.asyncio
async def test_non_stream_loop_rejects_missing_tool_payload():
    with pytest.raises(RuntimeError, match="finish_reason=tool_calls"):
        await run_chat_loop(
            provider=_MissingToolPayloadProvider(),
            tool_registry=ToolRegistry(),
            messages=[Message(Role.USER, "碰碰运气")],
            schemas=[],
        )


@pytest.mark.asyncio
async def test_stream_loop_emits_error_for_missing_tool_payload():
    events = [
        event
        async for event in run_chat_loop_stream(
            provider=_MissingToolPayloadProvider(),
            tool_registry=ToolRegistry(),
            messages=[Message(Role.USER, "碰碰运气")],
            schemas=[],
        )
    ]

    assert [event.kind for event in events] == [
        StreamEventKind.ROUND_START,
        StreamEventKind.ROUND_END,
        StreamEventKind.ERROR,
    ]
    assert "finish_reason=tool_calls" in events[-1].content


@pytest.mark.asyncio
async def test_stream_loop_executes_defaulted_dice_check_and_feeds_result_back():
    provider = _DiceThenNarrateStreamProvider()
    registry = ToolRegistry()
    registry.register(
        DiceCheckDCTool(
            DiceRoller(DiceModuleSettings(), rng=random.Random(4)),
            default_dc=13,
        )
    )

    events = [
        event
        async for event in run_chat_loop_stream(
            provider=provider,
            tool_registry=registry,
            messages=[Message(Role.USER, "碰碰运气找线索")],
            schemas=registry.get_openai_schemas(),
        )
    ]

    assert provider.calls == 2
    assert [event.kind for event in events] == [
        StreamEventKind.ROUND_START,
        StreamEventKind.ROUND_END,
        StreamEventKind.TOOL_CALL,
        StreamEventKind.TOOL_RESULT,
        StreamEventKind.ROUND_START,
        StreamEventKind.TEXT,
        StreamEventKind.ROUND_END,
        StreamEventKind.DONE,
    ]
    assert "expression=1d20" in (events[3].tool_result or "")
    assert "dc=13" in (events[3].tool_result or "")
    assert events[-1].content == "你在祭坛附近发现了一道新划痕。"
