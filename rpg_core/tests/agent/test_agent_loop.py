from __future__ import annotations

import random
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from llm_client.types import LLMResponse, ProviderChunk
import rpg_core.agent.turn.runner as runner_module
from rpg_core.agent.protocol import StreamEventKind
from rpg_core.agent.turn.runner import run_chat_loop, run_chat_loop_stream
from rpg_core.context.models import Message, Role
from rpg_core.rp_modules.dice.tools import DiceCheckDCTool, DiceRoller
from rpg_core.settings import DiceModuleSettings
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry


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


class _ReasoningDiceThenNarrateProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_default_model(self) -> str:
        return "reasoning-dice"

    async def chat(self, messages, tools=None):  # noqa: ANN001
        del tools
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                reasoning_content="先进行检定。",
                tool_calls=[{
                    "id": "call_reasoning_dice",
                    "function": {
                        "name": "rp_dice_check_dc",
                        "arguments": '{"reason":"搜索线索"}',
                    },
                }],
                finish_reason="tool_calls",
                model=self.get_default_model(),
            )
        assert any(
            message.get("role") == "assistant"
            and message.get("reasoning_content") == "先进行检定。"
            and message.get("tool_calls")
            for message in messages
        )
        assert any(message.get("role") == "tool" for message in messages)
        return LLMResponse(
            content="你找到了线索。",
            tool_calls=None,
            finish_reason="stop",
            model=self.get_default_model(),
        )

    async def chat_stream(self, messages, tools=None):  # noqa: ANN001
        del messages, tools
        raise AssertionError("non-stream test must not call chat_stream")


class _ReasoningDiceThenNarrateStreamProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_default_model(self) -> str:
        return "reasoning-dice-stream"

    async def chat(self, messages, tools=None):  # noqa: ANN001
        del messages, tools
        raise AssertionError("stream test must not call chat")

    async def chat_stream(self, messages, tools=None):  # noqa: ANN001
        del tools
        self.calls += 1
        if self.calls == 1:
            yield ProviderChunk(reasoning_content="先进行检定。")
            yield ProviderChunk(
                tool_calls=[{
                    "id": "call_reasoning_dice_stream",
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
            message.get("role") == "assistant"
            and message.get("reasoning_content") == "先进行检定。"
            and message.get("tool_calls")
            for message in messages
        )
        assert any(message.get("role") == "tool" for message in messages)
        yield ProviderChunk(content="你找到了线索。")
        yield ProviderChunk(finish_reason="stop", model=self.get_default_model())


class _LoggingTool(BaseTool):
    description = "Test verbose tool logging."

    def __init__(self, name: str, result: str) -> None:
        self.name = name
        self._result = result

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

    async def execute(self, **kwargs: object) -> str:
        del kwargs
        return self._result


class _ToolThenNarrateProvider:
    def __init__(self, tool_name: str, arguments: str) -> None:
        self._tool_name = tool_name
        self._arguments = arguments
        self.calls = 0

    def get_default_model(self) -> str:
        return "tool-logging"

    async def chat(self, messages, tools=None):  # noqa: ANN001
        del messages, tools
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[{
                    "id": "call_logging",
                    "function": {
                        "name": self._tool_name,
                        "arguments": self._arguments,
                    },
                }],
                finish_reason="tool_calls",
                model=self.get_default_model(),
            )
        return LLMResponse(
            content="done",
            tool_calls=None,
            finish_reason="stop",
            model=self.get_default_model(),
        )

    async def chat_stream(self, messages, tools=None):  # noqa: ANN001
        del messages, tools
        self.calls += 1
        if self.calls == 1:
            yield ProviderChunk(
                tool_calls=[{
                    "id": "call_logging_stream",
                    "function": {
                        "name": self._tool_name,
                        "arguments": self._arguments,
                    },
                }],
                finish_reason="tool_calls",
                model=self.get_default_model(),
            )
            return
        yield ProviderChunk(content="done")
        yield ProviderChunk(
            finish_reason="stop",
            model=self.get_default_model(),
        )


def _reasoning_dice_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        DiceCheckDCTool(
            DiceRoller(DiceModuleSettings(), rng=random.Random(4)),
            default_dc=13,
        )
    )
    return registry


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


@pytest.mark.asyncio
async def test_non_stream_loop_returns_reasoning_within_tool_chain_only():
    provider = _ReasoningDiceThenNarrateProvider()
    messages = [Message(Role.USER, "碰碰运气找线索")]

    reply, records = await run_chat_loop(
        provider=provider,
        tool_registry=_reasoning_dice_registry(),
        messages=messages,
        schemas=[],
    )

    assert provider.calls == 2
    assert reply == "你找到了线索。"
    assert records[0].reasoning_content == "先进行检定。"
    assert messages[1].reasoning_content == "先进行检定。"
    assert "reasoning_content" in messages[1].to_provider_dict()
    assert "reasoning_content" not in messages[1].to_persistence_dict()


@pytest.mark.asyncio
async def test_stream_loop_returns_reasoning_within_tool_chain_only():
    provider = _ReasoningDiceThenNarrateStreamProvider()
    messages = [Message(Role.USER, "碰碰运气找线索")]

    events = [
        event
        async for event in run_chat_loop_stream(
            provider=provider,
            tool_registry=_reasoning_dice_registry(),
            messages=messages,
            schemas=[],
        )
    ]

    assert provider.calls == 2
    assert [event.kind for event in events] == [
        StreamEventKind.ROUND_START,
        StreamEventKind.THINKING,
        StreamEventKind.ROUND_END,
        StreamEventKind.TOOL_CALL,
        StreamEventKind.TOOL_RESULT,
        StreamEventKind.ROUND_START,
        StreamEventKind.TEXT,
        StreamEventKind.ROUND_END,
        StreamEventKind.DONE,
    ]
    assert messages[1].reasoning_content == "先进行检定。"
    assert "reasoning_content" not in messages[1].to_persistence_dict()
    assert events[-1].content == "你找到了线索。"


@pytest.mark.parametrize("tool_name", ["history_search", "history_read"])
@pytest.mark.parametrize("stream", [False, True], ids=["sync", "stream"])
async def test_history_tool_verbose_logs_redact_arguments_and_results(
    monkeypatch,
    tool_name: str,
    stream: bool,
) -> None:
    secret_argument = "绝密搜索词"
    secret_result = "绝密历史正文"
    arguments = f'{{"value":"{secret_argument}"}}'
    result = f'{{"ok":true,"content":"{secret_result}"}}'
    provider = _ToolThenNarrateProvider(tool_name, arguments)
    registry = ToolRegistry()
    registry.register(_LoggingTool(tool_name, result))
    info = MagicMock()
    monkeypatch.setattr(
        runner_module,
        "settings",
        SimpleNamespace(verbose_logging=True, max_tool_calls=3),
    )
    monkeypatch.setattr(runner_module.logger, "info", info)

    if stream:
        _ = [
            event
            async for event in run_chat_loop_stream(
                provider=provider,
                tool_registry=registry,
                messages=[Message(Role.USER, "查询")],
                schemas=registry.get_openai_schemas(),
            )
        ]
    else:
        await run_chat_loop(
            provider=provider,
            tool_registry=registry,
            messages=[Message(Role.USER, "查询")],
            schemas=registry.get_openai_schemas(),
        )

    logged = repr(info.call_args_list)
    assert secret_argument not in logged
    assert secret_result not in logged
    assert f"<redacted chars={len(arguments)}>" in logged
    assert f"<redacted chars={len(result)}>" in logged


@pytest.mark.parametrize("stream", [False, True], ids=["sync", "stream"])
async def test_non_history_tool_verbose_logs_remain_unchanged(
    monkeypatch,
    stream: bool,
) -> None:
    tool_name = "ordinary_tool"
    arguments = '{"value":"visible argument"}'
    result = "visible result"
    provider = _ToolThenNarrateProvider(tool_name, arguments)
    registry = ToolRegistry()
    registry.register(_LoggingTool(tool_name, result))
    info = MagicMock()
    monkeypatch.setattr(
        runner_module,
        "settings",
        SimpleNamespace(verbose_logging=True, max_tool_calls=3),
    )
    monkeypatch.setattr(runner_module.logger, "info", info)

    if stream:
        _ = [
            event
            async for event in run_chat_loop_stream(
                provider=provider,
                tool_registry=registry,
                messages=[Message(Role.USER, "查询")],
                schemas=registry.get_openai_schemas(),
            )
        ]
    else:
        await run_chat_loop(
            provider=provider,
            tool_registry=registry,
            messages=[Message(Role.USER, "查询")],
            schemas=registry.get_openai_schemas(),
        )

    logged = repr(info.call_args_list)
    assert arguments in logged
    assert result in logged
    assert "<redacted" not in logged
