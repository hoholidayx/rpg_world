from __future__ import annotations

import asyncio

import pytest

from llm_client.keys import AGENT_MAIN_BIZ_KEY
from rpg_core import settings as settings_module
from rpg_core.agent.tools.history import (
    HISTORY_READ_TOOL_NAME,
    HISTORY_SEARCH_TOOL_NAME,
)
from rpg_core.agent.tools.summary import (
    SUMMARY_READ_TOOL_NAME,
    SUMMARY_SEARCH_TOOL_NAME,
)
from rpg_core.summary.batch_store import BatchSummaryStore
from tests.support.live_agent import (
    first_call_with_tools,
    main_tool_call_names,
    main_tool_invocations,
    persisted_turn,
)

pytestmark = [pytest.mark.integration, pytest.mark.live_llm]


@pytest.fixture
def _lookup_tools_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        type(settings_module.settings),
        "lookup_tools_enabled",
        property(lambda _self: True),
    )


@pytest.fixture
def live_lookup_harness(_lookup_tools_enabled, live_demo_harness):
    return live_demo_harness


def _assert_ooc_turn_is_cleanly_persisted(
    gateway,
    *,
    session_id: str,
    turn_id: int,
) -> None:
    rows = persisted_turn(gateway, session_id, turn_id)
    assert [(row.role, row.mode) for row in rows] == [
        ("user", "ooc"),
        ("assistant", "ooc"),
    ]
    assert all(not row.tool_call_id and not row.tool_calls_json for row in rows)
    backup_rows = [
        row
        for row in gateway.backup.messages.list(session_id)
        if row.turn_id == turn_id
    ]
    assert [(row.role, row.mode) for row in backup_rows] == [
        ("user", "ooc"),
        ("assistant", "ooc"),
    ]
    assert all(
        not row.tool_call_id and not row.tool_calls_json
        for row in backup_rows
    )


@pytest.mark.asyncio
async def test_live_llm_searches_then_reads_exact_committed_history(
    live_lookup_harness,
    integration_data_gateway,
) -> None:
    harness = live_lookup_harness
    user_input = (
        "先暂停故事，帮我从原始聊天记录精确核对一件事："
        "莫兰第一次查到东塔地下库最近一次调阅记录时，"
        "登记的具体时间是什么，签名处又是什么标记？"
        "请按原始记录回答，不要只凭剧情归纳，也不要推进剧情。"
    )

    reply = await asyncio.wait_for(
        harness.agent.send(user_input, mode="ooc"),
        timeout=180,
    )

    schema_call = first_call_with_tools(
        harness.calls,
        biz_key=AGENT_MAIN_BIZ_KEY,
        required_names={
            HISTORY_SEARCH_TOOL_NAME,
            HISTORY_READ_TOOL_NAME,
            SUMMARY_SEARCH_TOOL_NAME,
            SUMMARY_READ_TOOL_NAME,
        },
    )
    assert schema_call.tools

    names = main_tool_call_names(reply)
    assert HISTORY_SEARCH_TOOL_NAME in names
    assert HISTORY_READ_TOOL_NAME in names
    assert names.index(HISTORY_SEARCH_TOOL_NAME) < names.index(
        HISTORY_READ_TOOL_NAME
    )

    searches = main_tool_invocations(reply, HISTORY_SEARCH_TOOL_NAME)
    assert searches
    search_results = [
        invocation.result
        for invocation in searches
        if isinstance(invocation.result, dict)
    ]
    assert search_results
    assert all(result["ok"] is True for result in search_results)
    assert any(
        item.get("turnId") == 4
        for result in search_results
        for item in result.get("items", [])
    )

    reads = main_tool_invocations(reply, HISTORY_READ_TOOL_NAME)
    assert reads
    read_results = [
        invocation.result
        for invocation in reads
        if isinstance(invocation.result, dict)
    ]
    assert read_results
    assert all(result["ok"] is True for result in read_results)
    assert any(4 in result["turnIds"] for result in read_results)
    original_text = "\n".join(
        str(message.get("content", ""))
        for result in read_results
        for message in result["messages"]
    )
    assert "昨夜 23:10" in original_text
    assert "树枝烙印" in original_text

    assert "23:10" in reply.text
    assert "树枝" in reply.text
    assert reply.committed_turn_id is not None
    _assert_ooc_turn_is_cleanly_persisted(
        integration_data_gateway,
        session_id=harness.session_id,
        turn_id=reply.committed_turn_id,
    )


@pytest.mark.asyncio
async def test_live_llm_searches_then_reads_canonical_summary(
    live_lookup_harness,
    integration_data_gateway,
) -> None:
    harness = live_lookup_harness
    session_root = (
        integration_data_gateway.sessions.resolve_session_runtime_dir(
            harness.session_id
        )
    )
    store = BatchSummaryStore(session_root)
    try:
        store.save_overall(
            title="奥术学院调查阶段归纳",
            content=(
                "Alice 与莫兰追查灰袍监察员的一长两短联络节奏，随后抵达东塔侧门。"
                "黄铜把手异常发热，温度刻盘却被薄霜覆盖。恢复的记录显示昨夜 23:10 "
                "有人制造极低温，今天 13:47 又出现接近高烧的热度，两次都带有树枝烙印。"
                "进一步拓印显现了已注销监护人塞伦的姓名。"
            ),
            key_events=[
                "灰袍监察员留下旧巡林队联络节奏",
                "东塔侧门温度刻盘记录两次异常",
                "塞伦姓名通过拓印重新显现",
            ],
            last_batch_id=2,
        )
    finally:
        store.close()

    call_offset = len(harness.calls)
    user_input = (
        "先不推进故事。请从现有的阶段性剧情归纳里简短回顾一下："
        "从灰袍监察员出现，到塞伦的姓名重新显现，这一段发生了什么？"
        "这里只需要阶段性概括，不需要核对原始聊天的精确措辞或时间。"
        "请先查阅完整归纳再回答。"
    )
    reply = await asyncio.wait_for(
        harness.agent.send(user_input, mode="ooc"),
        timeout=180,
    )

    first_call_with_tools(
        harness.calls[call_offset:],
        biz_key=AGENT_MAIN_BIZ_KEY,
        required_names={SUMMARY_SEARCH_TOOL_NAME, SUMMARY_READ_TOOL_NAME},
    )
    names = main_tool_call_names(reply)
    assert SUMMARY_SEARCH_TOOL_NAME in names
    assert SUMMARY_READ_TOOL_NAME in names
    assert names.index(SUMMARY_SEARCH_TOOL_NAME) < names.index(
        SUMMARY_READ_TOOL_NAME
    )

    searches = main_tool_invocations(reply, SUMMARY_SEARCH_TOOL_NAME)
    assert searches
    search_results = [
        invocation.result
        for invocation in searches
        if isinstance(invocation.result, dict)
        and invocation.result.get("ok") is True
    ]
    assert search_results
    summary_item = next(
        item
        for result in search_results
        for item in result["items"]
        if item.get("summaryId") == "overall"
    )
    assert summary_item["resolvedTurnRange"] == {
        "start": 1,
        "end": 10,
        "source": "sql",
    }

    reads = main_tool_invocations(reply, SUMMARY_READ_TOOL_NAME)
    assert reads
    read_result = next(
        invocation.result
        for invocation in reads
        if isinstance(invocation.result, dict)
        and invocation.result.get("ok") is True
        and invocation.result.get("summaryId") == "overall"
    )
    assert read_result["resolvedTurnRange"] == {
        "start": 1,
        "end": 10,
        "source": "sql",
    }
    assert "昨夜 23:10" in read_result["content"]
    assert "今天 13:47" in read_result["content"]
    assert "塞伦" in read_result["content"]

    assert "灰袍" in reply.text
    assert "东塔侧门" in reply.text
    assert "塞伦" in reply.text
    assert reply.committed_turn_id is not None
    _assert_ooc_turn_is_cleanly_persisted(
        integration_data_gateway,
        session_id=harness.session_id,
        turn_id=reply.committed_turn_id,
    )
