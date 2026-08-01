from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

import rpg_core.agent.turn.runner as runner_module
from llm_client.types import LLMResponse, ProviderChunk
from rpg_core.agent.protocol import StreamEventKind
from rpg_core.agent.turn.projection import MainRoundProjection
from rpg_core.agent.turn.runner import run_chat_loop, run_chat_loop_stream
from rpg_core.context import FixedLayerSection
from rpg_core.context.models import (
    FixedLayerData,
    RPGContext,
    RPModuleRuntimeSection,
    RPModulesLayer,
    UserMessageLayer,
)
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry


class _OutcomeTool(BaseTool):
    name = "rp_story_outcome"
    description = "test outcome"

    def __init__(self, state: dict[str, object]) -> None:
        self._state = state

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        }

    async def execute(self, **kwargs: object) -> str:
        self._state["calls"] = int(self._state["calls"]) + 1
        self._state["staged"] = True
        return f'{{"outcomeCode":"success","reason":"{kwargs["reason"]}"}}'


def _projection_fixture() -> tuple[
    MainRoundProjection,
    ToolRegistry,
    list,
    dict[str, object],
]:
    state: dict[str, object] = {"staged": False, "calls": 0}
    registry = ToolRegistry()
    registry.register(_OutcomeTool(state))

    def sections() -> list[RPModuleRuntimeSection]:
        if state["staged"]:
            return [RPModuleRuntimeSection(
                id="rp_module_narrative_outcome_turn_directive",
                title="本轮最终剧情结果",
                content="FINAL_OUTCOME_ONLY",
            )]
        return [RPModuleRuntimeSection(
            id="rp_module_narrative_outcome_turn_directive",
            title="剧情分支随机裁定",
            content="PENDING_OUTCOME_CONTRACT",
        )]

    base_context = RPGContext(
        fixed_layer=FixedLayerData(sections=[FixedLayerSection(
            id="stable_fixed",
            title="Stable fixed",
            content="FIXED_MUST_NOT_CHANGE",
        )]),
        rp_modules=RPModulesLayer(sections=sections()),
        user_message=UserMessageLayer(user_input="尝试说服守卫"),
    )

    def schemas() -> list[dict] | None:
        if state["staged"]:
            return None
        return registry.get_openai_schemas()

    projection = MainRoundProjection(
        base_context=base_context,
        runtime_sections=sections,
        tool_registry=registry,
        schemas=schemas,
    )
    return projection, registry, projection.messages_for_round(()), state


class _ProjectedProvider:
    def __init__(self, *, stream: bool) -> None:
        self.stream = stream
        self.calls: list[tuple[list[dict], list[dict] | None]] = []

    def get_default_model(self) -> str:
        return "projection-test"

    def _capture(self, messages, tools) -> int:  # noqa: ANN001
        self.calls.append((messages, tools))
        return len(self.calls)

    async def chat(self, messages, tools=None):  # noqa: ANN001
        assert not self.stream
        call = self._capture(messages, tools)
        if call == 1:
            return LLMResponse(
                content="",
                tool_calls=_duplicate_outcome_calls(),
                finish_reason="tool_calls",
                model=self.get_default_model(),
            )
        return LLMResponse(
            content="裁定后的最终正文",
            tool_calls=None,
            finish_reason="stop",
            model=self.get_default_model(),
        )

    async def chat_stream(self, messages, tools=None) -> AsyncIterator[ProviderChunk]:  # noqa: ANN001
        assert self.stream
        call = self._capture(messages, tools)
        if call == 1:
            yield ProviderChunk(
                tool_calls=[
                    {**tool_call, "index": index}
                    for index, tool_call in enumerate(_duplicate_outcome_calls())
                ],
                finish_reason="tool_calls",
                model=self.get_default_model(),
            )
            return
        yield ProviderChunk(content="裁定后的最终正文")
        yield ProviderChunk(
            finish_reason="stop",
            model=self.get_default_model(),
        )


def _duplicate_outcome_calls() -> list[dict]:
    return [
        {
            "id": "outcome_1",
            "function": {
                "name": "rp_story_outcome",
                "arguments": '{"reason":"说服守卫"}',
            },
        },
        {
            "id": "outcome_2",
            "function": {
                "name": "rp_story_outcome",
                "arguments": '{"reason":"重复抽取"}',
            },
        },
    ]


def _assert_round_projection(
    provider: _ProjectedProvider,
    state: dict[str, object],
    tool_results: list[str],
) -> None:
    assert state == {"staged": True, "calls": 1}
    assert tool_results[0].startswith('{"outcomeCode":"success"')
    assert tool_results[1] == "Error: unknown tool 'rp_story_outcome'"
    assert len(provider.calls) == 2

    first_messages, first_tools = provider.calls[0]
    second_messages, second_tools = provider.calls[1]
    first_fixed = next(
        message["content"]
        for message in first_messages
        if "FIXED_MUST_NOT_CHANGE" in str(message.get("content"))
    )
    second_fixed = next(
        message["content"]
        for message in second_messages
        if "FIXED_MUST_NOT_CHANGE" in str(message.get("content"))
    )
    assert first_fixed == second_fixed
    assert any(
        "PENDING_OUTCOME_CONTRACT" in str(message.get("content"))
        for message in first_messages
    )
    assert not any(
        "PENDING_OUTCOME_CONTRACT" in str(message.get("content"))
        for message in second_messages
    )
    assert any(
        "FINAL_OUTCOME_ONLY" in str(message.get("content"))
        for message in second_messages
    )
    assert [schema["function"]["name"] for schema in first_tools or []] == [
        "rp_story_outcome"
    ]
    assert second_tools is None


@pytest.mark.asyncio
async def test_sync_round_projection_replaces_outcome_and_rejects_same_batch_repeat(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runner_module,
        "settings",
        type("Settings", (), {"max_tool_calls": 3, "verbose_logging": False})(),
    )
    projection, registry, messages, state = _projection_fixture()
    provider = _ProjectedProvider(stream=False)

    reply, records = await run_chat_loop(
        provider=provider,  # type: ignore[arg-type]
        tool_registry=registry,
        messages=messages,
        schemas=projection.schemas_for_round(),
        round_projection=projection,
    )

    assert reply == "裁定后的最终正文"
    _assert_round_projection(
        provider,
        state,
        [str(item["content"]) for item in records[0].tool_results],
    )


@pytest.mark.asyncio
async def test_stream_round_projection_replaces_outcome_and_rejects_same_batch_repeat(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runner_module,
        "settings",
        type("Settings", (), {"max_tool_calls": 3, "verbose_logging": False})(),
    )
    projection, registry, messages, state = _projection_fixture()
    provider = _ProjectedProvider(stream=True)

    events = [
        event
        async for event in run_chat_loop_stream(
            provider=provider,  # type: ignore[arg-type]
            tool_registry=registry,
            messages=messages,
            schemas=projection.schemas_for_round(),
            round_projection=projection,
        )
    ]

    assert events[-1].kind is StreamEventKind.DONE
    assert events[-1].content == "裁定后的最终正文"
    _assert_round_projection(
        provider,
        state,
        [
            str(event.tool_result)
            for event in events
            if event.kind is StreamEventKind.TOOL_RESULT
        ],
    )
