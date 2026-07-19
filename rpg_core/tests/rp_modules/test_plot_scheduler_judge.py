from __future__ import annotations

import pytest

from llm_client.types import LLMResponse
from rpg_core.agent.telemetry import TurnStats
from rpg_core.context.models import Message, Role
from rpg_core.rp_modules.plot_scheduler.judge import (
    PlotScheduleJudge,
    PlotScheduleJudgeResponseError,
)
from rpg_core.rp_modules.plot_scheduler.models import (
    PLOT_SUITABILITY_REASON_MAX_CHARS,
)


class _Provider:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response
        self.calls = []

    async def chat(self, messages, tools=None):  # noqa: ANN001, ANN201
        self.calls.append((messages, tools))
        return self.response

    @staticmethod
    def get_default_model() -> str:
        return "judge-model"


@pytest.mark.asyncio
async def test_plot_judge_requires_and_parses_structured_tool_result() -> None:
    provider = _Provider(LLMResponse(
        content="",
        tool_calls=[{
            "id": "call_1",
            "function": {
                "name": "plot_schedule_decision",
                "arguments": '{"suitable":true,"reason":"地点一致"}',
            },
        }],
        finish_reason="tool_calls",
        model="judge-model",
    ))

    decision = await PlotScheduleJudge(
        provider_factory=lambda: _provider_result(provider)
    ).judge([Message(Role.USER, "行动")], turn_stats=TurnStats())

    assert decision.suitable is True
    assert decision.reason == "地点一致"
    assert provider.calls[0][1][0]["function"]["name"] == "plot_schedule_decision"


@pytest.mark.asyncio
async def test_plot_judge_rejects_content_only_response() -> None:
    provider = _Provider(LLMResponse(
        content="适合",
        tool_calls=None,
        finish_reason="stop",
    ))

    with pytest.raises(PlotScheduleJudgeResponseError, match="tool call"):
        await PlotScheduleJudge(
            provider_factory=lambda: _provider_result(provider)
        ).judge([Message(Role.USER, "行动")], turn_stats=TurnStats())


@pytest.mark.asyncio
async def test_plot_judge_rejects_unbounded_reason() -> None:
    provider = _Provider(LLMResponse(
        content="",
        tool_calls=[{
            "id": "call_1",
            "function": {
                "name": "plot_schedule_decision",
                "arguments": (
                    '{"suitable":true,"reason":"'
                    + "x" * (PLOT_SUITABILITY_REASON_MAX_CHARS + 1)
                    + '"}'
                ),
            },
        }],
        finish_reason="tool_calls",
    ))

    with pytest.raises(PlotScheduleJudgeResponseError, match="length limit"):
        await PlotScheduleJudge(
            provider_factory=lambda: _provider_result(provider)
        ).judge([Message(Role.USER, "行动")], turn_stats=TurnStats())


async def _provider_result(provider):  # noqa: ANN001, ANN201
    return provider
