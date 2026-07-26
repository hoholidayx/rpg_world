from __future__ import annotations

import json

import pytest

from llm_client.types import ProviderChunk
from rpg_core.agent.protocol import StreamEventKind
from tests.support.scripted_llm import response, tool_call

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_sync_history_tools_search_then_read_without_persisting_tool_messages(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
) -> None:
    session_id = "integration_history_sync"
    agent = await integration_agent_factory(session_id)
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response(
            "艾琳答应在钟楼顶层等待。",
            model="config-model",
        )
    )
    first = await agent.send("我和艾琳约定在钟楼会合。")
    assert first.committed_turn_id == 1

    provider.queue_chat(
        response(
            "",
            model="config-model",
            tool_calls=[
                tool_call(
                    "history_search",
                    json.dumps(
                        {"terms": ["艾琳", "钟楼"], "limit": 5},
                        ensure_ascii=False,
                    ),
                    call_id="history_search_sync",
                )
            ],
            finish_reason="tool_calls",
        ),
        response(
            "",
            model="config-model",
            tool_calls=[
                tool_call(
                    "history_read",
                    '{"turn_id":1,"before_turns":1,"after_turns":1}',
                    call_id="history_read_sync",
                )
            ],
            finish_reason="tool_calls",
        ),
        response("已复核第一轮约定。", model="config-model"),
    )

    reply = await agent.send("请根据原始历史复核约定。", mode="ooc")

    assert reply.text == "已复核第一轮约定。"
    assert reply.committed_turn_id == 2
    assert reply.tool_records is not None
    assert len(reply.tool_records) == 2
    search_result = json.loads(
        str(reply.tool_records[0].tool_results[0]["content"])
    )
    assert search_result["ok"] is True
    assert [item["turnId"] for item in search_result["items"]] == [1]
    assert search_result["items"][0]["matchedTerms"] == ["艾琳", "钟楼"]

    read_result = json.loads(
        str(reply.tool_records[1].tool_results[0]["content"])
    )
    assert read_result["ok"] is True
    assert read_result["anchorTurnId"] == 1
    assert read_result["turnIds"] == [1]
    assert [message["content"] for message in read_result["messages"]] == [
        "我和艾琳约定在钟楼会合。",
        "艾琳答应在钟楼顶层等待。",
    ]

    rows = integration_data_gateway.messages.list(session_id)
    assert [(row.turn_id, row.role) for row in rows] == [
        (1, "user"),
        (1, "assistant"),
        (2, "user"),
        (2, "assistant"),
    ]
    assert all(not row.tool_call_id and not row.tool_calls_json for row in rows)
    assert [
        (row.turn_id, row.role)
        for row in integration_data_gateway.backup.messages.list(session_id)
    ] == [
        (1, "user"),
        (1, "assistant"),
        (2, "user"),
        (2, "assistant"),
    ]


@pytest.mark.asyncio
async def test_stream_history_tools_match_sync_contract_and_emit_tool_events(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
) -> None:
    session_id = "integration_history_stream"
    agent = await integration_agent_factory(session_id)
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response(
            "守门人把银钥匙交给了玩家。",
            model="config-model",
        )
    )
    await agent.send("我在北门见到守门人并取得银钥匙。")

    provider.queue_stream(
        (
            ProviderChunk(
                tool_calls=[
                    {
                        "index": 0,
                        **tool_call(
                            "history_search",
                            json.dumps(
                                {"terms": ["守门人", "银钥匙"]},
                                ensure_ascii=False,
                            ),
                            call_id="history_search_stream",
                        ),
                    }
                ],
                finish_reason="tool_calls",
                model="config-model",
            ),
        ),
        (
            ProviderChunk(
                tool_calls=[
                    {
                        "index": 0,
                        **tool_call(
                            "history_read",
                            '{"turn_id":1,"before_turns":0,"after_turns":1}',
                            call_id="history_read_stream",
                        ),
                    }
                ],
                finish_reason="tool_calls",
                model="config-model",
            ),
        ),
        (
            ProviderChunk(content="流式历史复核完成。"),
            ProviderChunk(finish_reason="stop", model="config-model"),
        ),
    )

    events = [
        event
        async for event in agent.send_stream(
            "请流式复核银钥匙来源。",
            mode="ooc",
        )
    ]

    tool_results = [
        json.loads(event.tool_result or "{}")
        for event in events
        if event.kind is StreamEventKind.TOOL_RESULT
    ]
    assert [result["ok"] for result in tool_results] == [True, True]
    assert [item["turnId"] for item in tool_results[0]["items"]] == [1]
    assert tool_results[1]["turnIds"] == [1]
    assert [message["content"] for message in tool_results[1]["messages"]] == [
        "我在北门见到守门人并取得银钥匙。",
        "守门人把银钥匙交给了玩家。",
    ]
    assert events[-1].kind is StreamEventKind.DONE
    assert events[-1].content == "流式历史复核完成。"

    rows = integration_data_gateway.messages.list(session_id)
    assert [(row.turn_id, row.role) for row in rows] == [
        (1, "user"),
        (1, "assistant"),
        (2, "user"),
        (2, "assistant"),
    ]
    assert all(not row.tool_call_id and not row.tool_calls_json for row in rows)
    assert [
        (row.turn_id, row.role)
        for row in integration_data_gateway.backup.messages.list(session_id)
    ] == [
        (1, "user"),
        (1, "assistant"),
        (2, "user"),
        (2, "assistant"),
    ]
