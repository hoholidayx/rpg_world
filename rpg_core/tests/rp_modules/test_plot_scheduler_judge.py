from __future__ import annotations

import pytest

from llm_client.types import LLMResponse
from rpg_core.agent.telemetry import TurnStats
from rpg_core.agent.tools.history import HistoryToolSet
from rpg_core.agent.tools.lookup import LookupToolSet
from rpg_core.agent.tools.summary import SummaryToolSet
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


@pytest.mark.asyncio
async def test_plot_judge_can_read_committed_history_before_deciding() -> None:
    class QueryService:
        def __init__(self) -> None:
            self.searches: list[tuple[object, object]] = []

        async def search(
            self,
            *,
            terms: object,
            limit: object,
        ) -> dict[str, object]:
            self.searches.append((terms, limit))
            return {
                "ok": True,
                "items": [{"turnId": 8, "excerpt": "信使已抵达门厅"}],
            }

        async def read(self, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("this scenario only needs history_search")

    class SequenceProvider:
        def __init__(self) -> None:
            self.calls: list[
                tuple[list[dict[str, object]], list[dict[str, object]]]
            ] = []
            self.responses = [
                LLMResponse(
                    content="",
                    tool_calls=[{
                        "id": "plot_history",
                        "type": "function",
                        "function": {
                            "name": "history_search",
                            "arguments": '{"terms":["信使"],"limit":2}',
                        },
                    }],
                    finish_reason="tool_calls",
                ),
                LLMResponse(
                    content="",
                    tool_calls=[{
                        "id": "plot_terminal",
                        "type": "function",
                        "function": {
                            "name": "plot_schedule_decision",
                            "arguments": (
                                '{"suitable":true,"reason":"已提交历史确认信使在场"}'
                            ),
                        },
                    }],
                    finish_reason="tool_calls",
                    model="judge-model",
                ),
            ]

        async def chat(self, messages, tools=None):  # noqa: ANN001, ANN201
            self.calls.append((messages, list(tools or [])))
            return self.responses.pop(0)

        @staticmethod
        def get_default_model() -> str:
            return "judge-model"

    query = QueryService()
    summary_query = type(
        "SummaryQuery",
        (),
        {
            "search": lambda *_args, **_kwargs: _provider_result({"ok": True}),
            "read": lambda *_args, **_kwargs: _provider_result({"ok": True}),
        },
    )()
    provider = SequenceProvider()
    stats = TurnStats()

    decision = await PlotScheduleJudge(
        provider_factory=lambda: _provider_result(provider),
        lookup_tools=LookupToolSet(
            HistoryToolSet(query),  # type: ignore[arg-type]
            SummaryToolSet(summary_query),  # type: ignore[arg-type]
        ),
        max_lookup_tool_rounds=5,
    ).judge([Message(Role.USER, "判断候选事件")], turn_stats=stats)

    assert decision.suitable is True
    assert decision.reason == "已提交历史确认信使在场"
    assert query.searches == [(["信使"], 2)]
    assert len(provider.calls) == 2
    assert {
        schema["function"]["name"]
        for schema in provider.calls[0][1]
    } == {
        "history_search",
        "history_read",
        "summary_search",
        "summary_read",
        "plot_schedule_decision",
    }
    assert any(
        message["role"] == "tool" and "信使已抵达门厅" in message["content"]
        for message in provider.calls[1][0]
    )
    assert [record.source for record in stats.calls] == [
        "plot_scheduler",
        "plot_scheduler",
    ]


async def _provider_result(provider):  # noqa: ANN001, ANN201
    return provider
