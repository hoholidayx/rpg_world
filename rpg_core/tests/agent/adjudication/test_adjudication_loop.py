from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import rpg_core.agent.adjudication.loop as loop_module
from llm_client.types import LLMResponse
from rpg_core.agent.adjudication import run_adjudication_tool_loop
from rpg_core.agent.telemetry import TurnStats
from rpg_core.agent.tools.history import HistoryToolSet
from rpg_core.context.models import Message, Role


_TERMINAL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "terminal_decision",
        "description": "finish the test adjudication",
        "parameters": {
            "type": "object",
            "properties": {"accepted": {"type": "boolean"}},
            "required": ["accepted"],
            "additionalProperties": False,
        },
    },
}


def _tool_call(name: str, arguments: str, call_id: str) -> dict[str, object]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments,
        },
    }


class _QueryService:
    def __init__(self) -> None:
        self.searches: list[tuple[object, object]] = []
        self.reads: list[tuple[object, object, object]] = []

    async def search(self, *, terms: object, limit: object) -> dict[str, object]:
        self.searches.append((terms, limit))
        return {
            "ok": True,
            "items": [{"turnId": 7, "excerpt": "sensitive history excerpt"}],
        }

    async def read(
        self,
        *,
        turn_id: object,
        before_turns: object,
        after_turns: object,
    ) -> dict[str, object]:
        self.reads.append((turn_id, before_turns, after_turns))
        return {
            "ok": True,
            "anchorTurnId": turn_id,
            "messages": [{"content": "sensitive complete history"}],
        }


class _Provider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[
            tuple[list[dict[str, object]], list[dict[str, object]]]
        ] = []

    async def chat(self, messages, tools=None):  # noqa: ANN001, ANN201
        self.calls.append((messages, list(tools or [])))
        return self._responses.pop(0)

    @staticmethod
    def get_default_model() -> str:
        return "adjudication-test"


@pytest.fixture(autouse=True)
def _quiet_loop_logs(monkeypatch):
    monkeypatch.setattr(
        loop_module,
        "settings",
        SimpleNamespace(verbose_logging=False),
    )


@pytest.mark.asyncio
async def test_history_search_read_then_terminal_preserves_transient_reasoning() -> None:
    query = _QueryService()
    provider = _Provider([
        LLMResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "history_search",
                    '{"terms":["旧誓言"],"limit":2}',
                    "search_1",
                )
            ],
            finish_reason="tool_calls",
            reasoning_content="先定位旧誓言。",
        ),
        LLMResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "history_read",
                    '{"turn_id":7,"before_turns":1,"after_turns":1}',
                    "read_1",
                )
            ],
            finish_reason="tool_calls",
            reasoning_content="再核对完整上下文。",
        ),
        LLMResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "terminal_decision",
                    '{"accepted":true}',
                    "terminal_1",
                )
            ],
            finish_reason="tool_calls",
        ),
    ])
    stats = TurnStats()

    result = await run_adjudication_tool_loop(
        provider=provider,
        messages=[Message(Role.SYSTEM, "authority"), Message(Role.USER, "decide")],
        terminal_schemas=[_TERMINAL_SCHEMA],
        source="status_router",
        history_tools=HistoryToolSet(query),  # type: ignore[arg-type]
        max_history_tool_rounds=5,
        turn_stats=stats,
    )

    assert result.history_rounds == 2
    assert len(result.call_records) == 3
    assert [record.source for record in stats.calls] == ["status_router"] * 3
    assert query.searches == [(["旧誓言"], 2)]
    assert query.reads == [(7, 1, 1)]
    second_messages = provider.calls[1][0]
    assert second_messages[-2]["reasoning_content"] == "先定位旧誓言。"
    assert second_messages[-1]["role"] == "tool"
    third_messages = provider.calls[2][0]
    assert third_messages[-2]["reasoning_content"] == "再核对完整上下文。"
    assert third_messages[-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_mixed_history_and_terminal_requires_a_fresh_terminal_decision() -> None:
    query = _QueryService()
    provider = _Provider([
        LLMResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "history_search",
                    '{"terms":["门厅"],"limit":1}',
                    "search_mixed",
                ),
                _tool_call(
                    "terminal_decision",
                    '{"accepted":false}',
                    "terminal_mixed",
                ),
            ],
            finish_reason="tool_calls",
        ),
        LLMResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "terminal_decision",
                    '{"accepted":true}',
                    "terminal_fresh",
                )
            ],
            finish_reason="tool_calls",
        ),
    ])

    result = await run_adjudication_tool_loop(
        provider=provider,
        messages=[Message(Role.USER, "decide")],
        terminal_schemas=[_TERMINAL_SCHEMA],
        source="plot_scheduler",
        history_tools=HistoryToolSet(query),  # type: ignore[arg-type]
        max_history_tool_rounds=5,
    )

    assert result.history_rounds == 1
    assert len(provider.calls) == 2
    followup_tool_messages = [
        message
        for message in provider.calls[1][0]
        if message["role"] == "tool"
    ]
    assert len(followup_tool_messages) == 2
    assert "sensitive history excerpt" in followup_tool_messages[0]["content"]
    assert "terminal_tool_mixed_with_history" in followup_tool_messages[1]["content"]
    final_calls = result.response.tool_calls
    assert final_calls is not None
    assert final_calls[0]["id"] == "terminal_fresh"


@pytest.mark.asyncio
async def test_five_history_rounds_are_followed_by_one_terminal_only_call() -> None:
    query = _QueryService()
    responses = [
        LLMResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "history_search",
                    f'{{"terms":["线索{i}"],"limit":1}}',
                    f"search_{i}",
                )
            ],
            finish_reason="tool_calls",
        )
        for i in range(5)
    ]
    responses.append(LLMResponse(
        content="",
        tool_calls=[
            _tool_call(
                "terminal_decision",
                '{"accepted":true}',
                "terminal_after_budget",
            )
        ],
        finish_reason="tool_calls",
    ))
    provider = _Provider(responses)

    result = await run_adjudication_tool_loop(
        provider=provider,
        messages=[Message(Role.USER, "decide")],
        terminal_schemas=[_TERMINAL_SCHEMA],
        source="status_update:scene",
        history_tools=HistoryToolSet(query),  # type: ignore[arg-type]
        max_history_tool_rounds=5,
    )

    assert result.history_rounds == 5
    assert len(provider.calls) == 6
    for _messages, schemas in provider.calls[:5]:
        assert {
            schema["function"]["name"]
            for schema in schemas
        } == {"history_search", "history_read", "terminal_decision"}
    assert [
        schema["function"]["name"]
        for schema in provider.calls[5][1]
    ] == ["terminal_decision"]
    assert any(
        "历史查询轮次已经用尽" in message["content"]
        for message in provider.calls[5][0]
        if message["role"] == "system"
    )


@pytest.mark.asyncio
async def test_history_arguments_and_results_are_redacted_from_verbose_logs(
    monkeypatch,
) -> None:
    query = _QueryService()
    provider = _Provider([
        LLMResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "history_search",
                    '{"terms":["绝密名字"],"limit":1}',
                    "search_secret",
                )
            ],
            finish_reason="tool_calls",
        ),
        LLMResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "terminal_decision",
                    '{"accepted":true}',
                    "terminal_secret",
                )
            ],
            finish_reason="tool_calls",
        ),
    ])
    info = MagicMock()
    monkeypatch.setattr(
        loop_module,
        "settings",
        SimpleNamespace(verbose_logging=True),
    )
    monkeypatch.setattr(loop_module.logger, "info", info)

    await run_adjudication_tool_loop(
        provider=provider,
        messages=[Message(Role.USER, "decide")],
        terminal_schemas=[_TERMINAL_SCHEMA],
        source="status_outcome_preflight",
        history_tools=HistoryToolSet(query),  # type: ignore[arg-type]
        max_history_tool_rounds=5,
    )

    logged = "\n".join(
        repr((call.args, call.kwargs))
        for call in info.call_args_list
    )
    assert "绝密名字" not in logged
    assert "sensitive history excerpt" not in logged
    assert "<redacted chars=" in logged
