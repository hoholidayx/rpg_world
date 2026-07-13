from __future__ import annotations

import asyncio

import pytest

from llm_service.types import ProviderChunk
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnCancelStatus
from rpg_core.agent.transaction.status_scratch import StatusDocumentScratch
from rpg_core.tests.integration.scripted_llm import response, tool_call

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_non_stream_provider_failure_discards_everything_and_reuses_turn_id(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(RuntimeError("scripted chat failure"))

    with pytest.raises(RuntimeError, match="scripted chat failure"):
        await integration_agent.send("this turn must fail")

    assert integration_agent.history == []
    assert integration_data_gateway.messages.count("integration_smoke") == 0
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 0

    reply = await integration_agent.send("retry")

    assert reply.text == "config-model response"
    rows = integration_data_gateway.messages.list("integration_smoke")
    assert [(row.turn_id, row.seq_in_turn) for row in rows] == [(1, 1), (1, 2)]


@pytest.mark.asyncio
async def test_stream_provider_failure_emits_error_without_committing_partial_turn(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    scripted_llm_manager.main_provider().queue_stream(RuntimeError("scripted stream failure"))

    events = [event async for event in integration_agent.send_stream("stream must fail")]

    assert [event.kind for event in events] == [
        StreamEventKind.ROUND_START,
        StreamEventKind.ERROR,
    ]
    assert events[-1].content == "scripted stream failure"
    assert integration_agent.history == []
    assert integration_data_gateway.messages.count("integration_smoke") == 0
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 0

    await integration_agent.send("retry after stream failure")
    assert [row.turn_id for row in integration_data_gateway.messages.list("integration_smoke")] == [1, 1]


@pytest.mark.asyncio
async def test_empty_stream_completion_persists_a_complete_message_pair(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    scripted_llm_manager.main_provider().queue_stream(())

    events = [event async for event in integration_agent.send_stream("empty response")]

    assert [event.kind for event in events] == [
        StreamEventKind.ROUND_START,
        StreamEventKind.ROUND_END,
        StreamEventKind.DONE,
    ]
    rows = integration_data_gateway.messages.list("integration_smoke")
    assert [(row.role, row.content) for row in rows] == [
        ("user", "empty response"),
        ("assistant", ""),
    ]
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 2


@pytest.mark.asyncio
async def test_stream_loop_without_done_is_treated_as_failed_turn(
    integration_agent,
    integration_data_gateway,
    monkeypatch,
):
    async def incomplete_loop(**_kwargs):
        yield AgentStreamEvent(kind=StreamEventKind.ROUND_START)

    monkeypatch.setattr(
        integration_agent._turn_service._orchestrator,
        "_stream_runner",
        incomplete_loop,
    )

    events = [event async for event in integration_agent.send_stream("missing done")]

    assert [event.kind for event in events] == [
        StreamEventKind.ROUND_START,
        StreamEventKind.ERROR,
    ]
    assert events[-1].content == "LLM stream ended without a DONE event"
    assert integration_data_gateway.messages.count("integration_smoke") == 0
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 0


@pytest.mark.asyncio
async def test_active_stream_cancellation_discards_turn_and_keeps_agent_usable(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    started = asyncio.Event()
    release = asyncio.Event()

    async def gated_stream(_messages, _tools):
        started.set()
        await release.wait()
        return (
            ProviderChunk(content="too late"),
            ProviderChunk(finish_reason="stop", model="config-model"),
        )

    scripted_llm_manager.main_provider().queue_stream(gated_stream)
    events = []

    async def consume() -> None:
        async for event in integration_agent.send_stream("wait", request_id="req_cancel"):
            events.append(event)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=2)
    result = await integration_agent.cancel_current_turn(request_id="req_cancel")
    await asyncio.wait_for(task, timeout=2)

    assert result.status == TurnCancelStatus.CANCELLED
    assert all(event.kind != StreamEventKind.DONE for event in events)
    assert integration_data_gateway.messages.count("integration_smoke") == 0
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 0

    await integration_agent.send("works after cancellation")
    assert [row.turn_id for row in integration_data_gateway.messages.list("integration_smoke")] == [1, 1]


@pytest.mark.asyncio
async def test_status_scratch_and_messages_commit_together_with_real_sqlite(
    integration_status_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    table = integration_status_agent._lifecycle.resources.status_manager.list_context_tables()[0]
    table_id = int(table["id"])
    scripted_llm_manager.status.queue_chat(response("", model="status-model"))
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[tool_call(
                "select_status_targets",
                f'{{"scene":false,"tables":[{{"table_id":{table_id},"realtime_keys":["线索"],"event_keys":[],"reason":"明确更新线索"}}]}}',
            )],
        )
    )
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call(
                    "status_table_set_values",
                    f'{{"table_id":{table_id},"updates":[{{"key":"线索","value":"已更新"}}]}}',
                )
            ],
        )
    )

    reply = await integration_status_agent.send("更新线索")

    assert reply.status_sub_agent_records
    assert reply.status_sub_agent_records[0]["changed"] is True
    persisted = integration_data_gateway.status.get_table_for_session(
        "integration_status",
        table_id,
    )
    assert persisted.document.row_for_key("线索").value == "已更新"
    assert integration_data_gateway.messages.count("integration_status") == 2
    assert integration_data_gateway.backup.messages.count("integration_status") == 2
    main_call = scripted_llm_manager.main_provider().calls[-1]
    assert "已更新" in "\n".join(message.get("content", "") for message in main_call.messages)


@pytest.mark.asyncio
async def test_status_target_failure_keeps_successful_scene_and_main_turn_running(
    integration_status_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    status_manager = integration_status_agent._lifecycle.resources.status_manager
    table = status_manager.list_context_tables()[0]
    table_id = int(table["id"])
    scripted_llm_manager.status.queue_chat(
        response("", model="status-model"),
        response(
            "",
            model="status-model",
            tool_calls=[tool_call(
                "select_status_targets",
                f'{{"scene":true,"tables":[{{"table_id":{table_id},'
                '"realtime_keys":["线索"],"event_keys":[],'
                '"reason":"确定更新线索"}]}',
            )],
        ),
        response(
            "",
            model="status-model",
            tool_calls=[tool_call(
                "scene_attr",
                '{"key":"位置","value":"部分成功现场"}',
            )],
        ),
        RuntimeError("normal table provider unavailable"),
    )

    reply = await integration_status_agent.send("移动并更新线索")

    assert reply.status_sub_agent_records
    assert reply.status_sub_agent_records[0]["status"] == "changed"
    assert len(scripted_llm_manager.main_provider().calls) == 1
    main_context = "\n".join(
        str(message.get("content", ""))
        for message in scripted_llm_manager.main_provider().calls[0].messages
    )
    assert "部分成功现场" in main_context
    scene_attrs = integration_data_gateway.status.get_scene_attrs("integration_status")
    assert scene_attrs is not None
    assert scene_attrs["位置"] == "部分成功现场"
    persisted = integration_data_gateway.status.get_table_for_session(
        "integration_status",
        table_id,
    )
    assert persisted.document.row_for_key("线索").value == "状态表已挂载"
    assert integration_data_gateway.messages.count("integration_status") == 2


@pytest.mark.asyncio
async def test_main_failure_discards_successful_partial_status_prewrites(
    integration_status_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    status_manager = integration_status_agent._lifecycle.resources.status_manager
    table = status_manager.list_context_tables()[0]
    table_id = int(table["id"])
    scripted_llm_manager.status.queue_chat(
        response("", model="status-model"),
        response(
            "",
            model="status-model",
            tool_calls=[tool_call(
                "select_status_targets",
                f'{{"scene":true,"tables":[{{"table_id":{table_id},'
                '"realtime_keys":["线索"],"event_keys":[],'
                '"reason":"确定更新线索"}]}',
            )],
        ),
        response(
            "",
            model="status-model",
            tool_calls=[tool_call(
                "scene_attr",
                '{"key":"位置","value":"不应提交的场景"}',
            )],
        ),
        RuntimeError("normal table provider unavailable"),
    )
    scripted_llm_manager.main_provider().queue_chat(
        RuntimeError("main provider unavailable")
    )

    with pytest.raises(RuntimeError, match="main provider unavailable"):
        await integration_status_agent.send("移动后主流程失败")

    scene_attrs = integration_data_gateway.status.get_scene_attrs("integration_status")
    assert scene_attrs is not None
    assert scene_attrs["位置"] == "集成测试大厅"
    persisted = integration_data_gateway.status.get_table_for_session(
        "integration_status",
        table_id,
    )
    assert persisted.document.row_for_key("线索").value == "状态表已挂载"
    assert integration_data_gateway.messages.count("integration_status") == 0
    assert integration_data_gateway.backup.messages.count("integration_status") == 0


@pytest.mark.asyncio
async def test_status_commit_failure_rolls_back_messages_backup_and_document(
    integration_status_agent,
    integration_data_gateway,
    scripted_llm_manager,
    monkeypatch,
):
    status_manager = integration_status_agent._lifecycle.resources.status_manager
    table = status_manager.list_context_tables()[0]
    table_id = int(table["id"])
    scripted_llm_manager.status.queue_chat(response("", model="status-model"))
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[tool_call(
                "select_status_targets",
                f'{{"scene":false,"tables":[{{"table_id":{table_id},"realtime_keys":["线索"],"event_keys":[],"reason":"明确更新线索"}}]}}',
            )],
        )
    )
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call(
                    "status_table_set_values",
                    f'{{"table_id":{table_id},"updates":[{{"key":"线索","value":"不应落库"}}]}}',
                )
            ],
        )
    )

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("forced status commit failure")

    monkeypatch.setattr(status_manager, "save_table_document", fail_save)

    with pytest.raises(RuntimeError, match="forced status commit failure"):
        await integration_status_agent.send("触发回滚")

    persisted = integration_data_gateway.status.get_table_for_session(
        "integration_status",
        table_id,
    )
    assert persisted.document.row_for_key("线索").value == "状态表已挂载"
    assert integration_status_agent.history == []
    assert integration_data_gateway.messages.count("integration_status") == 0
    assert integration_data_gateway.backup.messages.count("integration_status") == 0


@pytest.mark.asyncio
async def test_post_commit_side_effect_failure_does_not_undo_successful_turn(
    integration_agent,
    integration_data_gateway,
    monkeypatch,
):
    async def fail_after_commit(_session):
        raise RuntimeError("post-commit failure")

    monkeypatch.setattr(
        integration_agent._lifecycle.memory_sub_agent,
        "maybe_auto_extract",
        fail_after_commit,
    )

    reply = await integration_agent.send("commit first")

    assert reply.text == "config-model response"
    assert integration_data_gateway.messages.count("integration_smoke") == 2
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 2


@pytest.mark.asyncio
async def test_main_agent_story_outcome_round_trip_commits_record_and_only_final_messages(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response(
            "",
            model="config-model",
            tool_calls=[
                tool_call(
                    "rp_story_outcome",
                    '{"reason":"潜过巡逻守卫","actor":"Alice"}',
                )
            ],
        ),
        response("Alice 依照裁定结果行动。", model="config-model"),
    )

    reply = await integration_agent.send("我碰碰运气潜过巡逻守卫")

    assert reply.text == "Alice 依照裁定结果行动。"
    assert reply.tool_records and len(reply.tool_records) == 1
    assert len(provider.calls) == 2
    second_messages = provider.calls[1].messages
    tool_messages = [
        message for message in second_messages if message.get("role") == "tool"
    ]
    assert len(tool_messages) == 1
    assert '\"outcomeCode\"' in tool_messages[0].get("content", "")
    assert "sample" not in tool_messages[0].get("content", "")
    rp_tool_names = {
        schema["function"]["name"]
        for schema in provider.calls[0].tools or []
        if str(schema["function"]["name"]).startswith("rp_")
    }
    assert rp_tool_names == {"rp_story_outcome"}
    rows = integration_data_gateway.messages.list("integration_smoke")
    assert [(row.role, row.content) for row in rows] == [
        ("user", "我碰碰运气潜过巡逻守卫"),
        ("assistant", "Alice 依照裁定结果行动。"),
    ]
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 2
    outcome = integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    )
    assert outcome is not None
    assert outcome.reason == "潜过巡逻守卫"
    assert outcome.actor == "Alice"


class _SequenceRng:
    def __init__(self, *values: int) -> None:
        self.values = list(values)
        self.calls = 0

    def randint(self, lower: int, upper: int) -> int:
        assert (lower, upper) == (1, 100)
        self.calls += 1
        return self.values.pop(0)


def _set_outcome_rng(agent, *values: int) -> _SequenceRng:
    rng = _SequenceRng(*values)
    agent._lifecycle.rp_module_registry._rng_factory = lambda: rng
    return rng


@pytest.mark.asyncio
async def test_status_sub_agent_preadjudicates_before_first_main_call(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    rng = _set_outcome_rng(integration_agent, 31)
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call(
                    "rp_story_outcome",
                    '{"reason":"能否潜过巡逻守卫","actor":"Alice"}',
                )
            ],
        )
    )

    reply = await integration_agent.send("我趁阴影潜过巡逻守卫")

    assert rng.calls == 1
    assert reply.status_sub_agent_records
    assert reply.status_sub_agent_records[0]["status"] == "outcome_staged"
    assert len(scripted_llm_manager.status.calls) == 1
    assert len(scripted_llm_manager.main_provider().calls) == 1
    status_schema_names = {
        schema["function"]["name"]
        for schema in scripted_llm_manager.status.calls[0].tools or []
    }
    assert status_schema_names == {"rp_story_outcome"}
    main_schema_names = {
        schema["function"]["name"]
        for schema in scripted_llm_manager.main_provider().calls[0].tools or []
    }
    assert "rp_story_outcome" not in main_schema_names
    first_main_context = "\n".join(
        str(message.get("content", ""))
        for message in scripted_llm_manager.main_provider().calls[0].messages
    )
    assert '"outcomeCode":"success_with_cost"' in first_main_context
    assert '"reason":"能否潜过巡逻守卫"' in first_main_context
    assert "不得改判" in first_main_context
    assert "reason 是不可缩小的整体目标边界" in first_main_context
    assert "rp_story_outcome" not in first_main_context
    assert "scene_time、scene_attr、scene_del_attr" in first_main_context
    assert "status_table_set_values" in first_main_context
    assert "输出任何 RP 正文前调用" in first_main_context
    assert "工具调用轮不得夹带 RP 正文" in first_main_context
    assert "最终正文不得新增尚未同步的确定状态" in first_main_context
    assert "不得询问是否需要更新状态" in first_main_context
    assert "StatusSubAgent 已完成本轮剧情预裁定" not in first_main_context
    assert [call.source for call in reply.stats.calls] == [
        "status_outcome_preflight",
        "chat_loop",
    ]
    persisted = integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    )
    assert persisted is not None
    assert persisted.outcome_code == "success_with_cost"


@pytest.mark.asyncio
async def test_main_agent_syncs_scene_and_normal_status_after_preadjudication(
    integration_status_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    rng = _set_outcome_rng(integration_status_agent, 71)
    table = integration_status_agent._lifecycle.resources.status_manager.list_context_tables()[0]
    table_id = int(table["id"])
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call(
                    "rp_story_outcome",
                    '{"reason":"能否找到地下入口","actor":"Integration Tester"}',
                )
            ],
        )
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response(
            "",
            model="config-model",
            tool_calls=[
                tool_call(
                    "scene_attr",
                    '{"key":"位置","value":"地下裂隙"}',
                    call_id="call_scene_correction",
                ),
                tool_call(
                    "status_table_set_values",
                    f'{{"table_id":{table_id},"updates":[{{"key":"线索","value":"地下入口已确认"}}]}}',
                    call_id="call_status_correction",
                ),
            ],
        ),
        response("裁定结果已落实到场景与线索状态。", model="config-model"),
    )

    reply = await integration_status_agent.send("我寻找通往地下的入口")

    assert reply.text == "裁定结果已落实到场景与线索状态。"
    assert rng.calls == 1
    assert reply.status_sub_agent_records
    assert reply.status_sub_agent_records[0]["status"] == "outcome_staged"
    assert len(provider.calls) == 2
    scene_attrs = integration_data_gateway.status.get_scene_attrs("integration_status")
    assert scene_attrs is not None
    assert scene_attrs["位置"] == "地下裂隙"
    persisted_table = integration_data_gateway.status.get_table_for_session(
        "integration_status",
        table_id,
    )
    assert persisted_table.document.row_for_key("线索").value == "地下入口已确认"
    persisted_outcome = integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_status",
        1,
    )
    assert persisted_outcome is not None
    assert persisted_outcome.outcome_code == "setback"


@pytest.mark.asyncio
async def test_status_sub_agent_outcome_skips_mixed_state_prewrites(
    integration_status_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call(
                    "rp_story_outcome",
                    '{"reason":"能否找到隐藏线索"}',
                    call_id="call_outcome",
                ),
            ],
        )
    )

    reply = await integration_status_agent.send("我搜索隐藏线索")

    assert reply.status_sub_agent_records
    assert [record["status"] for record in reply.status_sub_agent_records] == [
        "outcome_staged",
    ]
    table = integration_status_agent._lifecycle.resources.status_manager.list_context_tables()[0]
    table_id = int(table["id"])
    persisted_table = integration_data_gateway.status.get_table_for_session(
        "integration_status",
        table_id,
    )
    assert persisted_table.document.row_for_key("线索").value == "状态表已挂载"
    main_context = "\n".join(
        str(message.get("content", ""))
        for message in scripted_llm_manager.main_provider().calls[0].messages
    )
    assert "状态表已挂载" in main_context
    assert "不应预写" not in main_context
    assert integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_status",
        1,
    ) is not None


@pytest.mark.asyncio
async def test_main_agent_cannot_reexecute_status_sub_agent_preadjudication(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    rng = _set_outcome_rng(integration_agent, 96)
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call("rp_story_outcome", '{"reason":"撬开封印"}')
            ],
        )
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response(
            "",
            model="config-model",
            tool_calls=[
                tool_call(
                    "rp_story_outcome",
                    '{"reason":"主 Agent 重复请求，不应重抽"}',
                )
            ],
        ),
        response("封印引发了严重反噬，但留下了继续调查的路径。", model="config-model"),
    )

    reply = await integration_agent.send("撬开封印")

    assert reply.text == "封印引发了严重反噬，但留下了继续调查的路径。"
    assert rng.calls == 1
    assert len(provider.calls) == 2
    assert reply.tool_records and len(reply.tool_records) == 1
    rejected_tool_result = reply.tool_records[0].tool_results[0]["content"]
    assert rejected_tool_result == "Error: unknown tool 'rp_story_outcome'"
    persisted = integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    )
    assert persisted is not None
    assert persisted.reason == "撬开封印"


@pytest.mark.asyncio
async def test_main_agent_fallback_adjudicates_after_status_sub_agent_failure(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    scripted_llm_manager.status.queue_chat(
        RuntimeError("status preflight unavailable")
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response(
            "",
            model="config-model",
            tool_calls=[
                tool_call(
                    "rp_story_outcome",
                    '{"reason":"能否避开守卫"}',
                )
            ],
        ),
        response("你避开了第一道视线，但脚步声引来了新的巡逻。", model="config-model"),
    )

    reply = await integration_agent.send("我碰碰运气避开守卫")

    assert reply.text == "你避开了第一道视线，但脚步声引来了新的巡逻。"
    assert reply.status_sub_agent_records is None
    assert len(provider.calls) == 2
    persisted = integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    )
    assert persisted is not None
    assert persisted.reason == "能否避开守卫"


@pytest.mark.asyncio
async def test_stream_emits_preadjudication_card_before_main_narration(
    integration_agent,
    scripted_llm_manager,
):
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call(
                    "rp_story_outcome",
                    '{"reason":"能否及时跃过断桥","actor":"Alice"}',
                )
            ],
        )
    )

    events = [
        event
        async for event in integration_agent.send_stream("我冲刺跃过断桥")
    ]

    assert [event.kind for event in events[:3]] == [
        StreamEventKind.TOOL_CALL,
        StreamEventKind.TOOL_RESULT,
        StreamEventKind.ROUND_START,
    ]
    assert events[0].tool_name == "rp_story_outcome"
    assert events[1].tool_name == "rp_story_outcome"
    assert '"outcomeCode"' in (events[1].tool_result or "")
    assert events[-1].kind == StreamEventKind.DONE
    assert events[-1].committed_turn_id == 1


@pytest.mark.asyncio
async def test_stream_syncs_state_before_success_with_cost_narration(
    integration_status_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    _set_outcome_rng(integration_status_agent, 31)
    table = integration_status_agent._lifecycle.resources.status_manager.list_context_tables()[0]
    table_id = int(table["id"])
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call(
                    "rp_story_outcome",
                    '{"reason":"Bob 和 Alice 离开祭坛并返回北境镇","actor":"Bob"}',
                )
            ],
        )
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_stream(
        (
            ProviderChunk(
                tool_calls=[
                    {
                        "index": 0,
                        **tool_call(
                            "scene_attr",
                            '{"key":"位置","value":"北境镇·旅店"}',
                            call_id="call_scene_town",
                        ),
                    },
                    {
                        "index": 1,
                        **tool_call(
                            "status_table_set_values",
                            f'{{"table_id":{table_id},"updates":[{{"key":"线索","value":"封印脉冲已释放，黑羽持续发热"}}]}}',
                            call_id="call_status_cost",
                        ),
                    },
                ],
                finish_reason="tool_calls",
                model="config-model",
            ),
        ),
        (
            ProviderChunk(
                content=(
                    "<rp-narration>Bob 和 Alice 已经回到北境镇的旅店，"
                    "但黑羽在途中一直发热，并留下了醒目的灼痕。</rp-narration>"
                )
            ),
            ProviderChunk(finish_reason="stop", model="config-model"),
        ),
    )

    events = [
        event
        async for event in integration_status_agent.send_stream(
            "已经有足够多的线索了，回镇子上再做打算吧。"
        )
    ]

    state_tool_indices = [
        index
        for index, event in enumerate(events)
        if event.kind == StreamEventKind.TOOL_CALL
        and event.tool_name in {"scene_attr", "status_table_set_values"}
    ]
    text_indices = [
        index
        for index, event in enumerate(events)
        if event.kind == StreamEventKind.TEXT and event.content
    ]
    assert len(state_tool_indices) == 2
    assert text_indices
    assert max(state_tool_indices) < min(text_indices)
    final = events[-1]
    assert final.kind == StreamEventKind.DONE
    assert final.committed_turn_id == 1
    assert "回到北境镇" in final.content
    assert "需要我标记" not in final.content
    scene_attrs = integration_data_gateway.status.get_scene_attrs("integration_status")
    assert scene_attrs is not None
    assert scene_attrs["位置"] == "北境镇·旅店"
    persisted_table = integration_data_gateway.status.get_table_for_session(
        "integration_status",
        table_id,
    )
    assert persisted_table.document.row_for_key("线索").value == "封印脉冲已释放，黑羽持续发热"
    persisted_outcome = integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_status",
        1,
    )
    assert persisted_outcome is not None
    assert persisted_outcome.outcome_code == "success_with_cost"


@pytest.mark.asyncio
async def test_outcome_commit_failure_rolls_back_record_messages_and_backup(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
    monkeypatch,
):
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call("rp_story_outcome", '{"reason":"撬开封印"}')
            ],
        )
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response("不会提交。", model="config-model"),
    )

    def fail_status_commit(*_args, **_kwargs):
        raise RuntimeError("forced final commit failure")

    monkeypatch.setattr(StatusDocumentScratch, "commit", fail_status_commit)

    with pytest.raises(RuntimeError, match="forced final commit failure"):
        await integration_agent.send("尝试撬开封印")

    assert integration_data_gateway.messages.count("integration_smoke") == 0
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 0
    assert integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    ) is None


@pytest.mark.asyncio
async def test_main_provider_failure_discards_status_preadjudication(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    scripted_llm_manager.status.queue_chat(
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call("rp_story_outcome", '{"reason":"穿过不稳定传送门"}')
            ],
        )
    )
    scripted_llm_manager.main_provider().queue_chat(
        RuntimeError("main failed after preadjudication")
    )

    with pytest.raises(RuntimeError, match="main failed after preadjudication"):
        await integration_agent.send("我穿过不稳定传送门")

    assert integration_data_gateway.messages.count("integration_smoke") == 0
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 0
    assert integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    ) is None


async def _gated_stream(started: asyncio.Event, release: asyncio.Event):
    started.set()
    await release.wait()
    return (
        ProviderChunk(content="too late"),
        ProviderChunk(finish_reason="stop", model="config-model"),
    )


@pytest.mark.asyncio
async def test_stream_cancel_after_outcome_tool_discards_staged_record(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    provider = scripted_llm_manager.main_provider()
    second_round_started = asyncio.Event()
    release = asyncio.Event()
    provider.queue_stream(
        (
            ProviderChunk(
                tool_calls=[
                    {
                        "index": 0,
                        **tool_call(
                            "rp_story_outcome",
                            '{"reason":"跃过断桥","actor":"Alice"}',
                        ),
                    }
                ],
                finish_reason="tool_calls",
                model="config-model",
            ),
        ),
        lambda _messages, _tools: _gated_stream(
            second_round_started,
            release,
        ),
    )
    events = []

    async def consume() -> None:
        async for event in integration_agent.send_stream(
            "跃过断桥",
            request_id="req_outcome_cancel",
        ):
            events.append(event)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(second_round_started.wait(), timeout=2)
    result = await integration_agent.cancel_current_turn(
        request_id="req_outcome_cancel"
    )
    await asyncio.wait_for(task, timeout=2)

    assert result.status == TurnCancelStatus.CANCELLED
    assert any(event.kind == StreamEventKind.TOOL_RESULT for event in events)
    assert integration_data_gateway.messages.count("integration_smoke") == 0
    assert integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    ) is None


@pytest.mark.asyncio
async def test_retry_truncate_deletes_outcome_and_draws_again(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    _set_outcome_rng(integration_agent, 1, 100)
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response(
            "",
            model="config-model",
            tool_calls=[tool_call("rp_story_outcome", '{"reason":"寻找密道"}')],
        ),
        response("第一次。", model="config-model"),
    )
    await integration_agent.send("寻找密道")
    first = integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    )
    assert first is not None
    assert first.outcome_code == "critical_success"

    await integration_agent.truncate_history_from_turn(1)
    assert integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    ) is None

    provider.queue_chat(
        response(
            "",
            model="config-model",
            tool_calls=[tool_call("rp_story_outcome", '{"reason":"寻找密道"}')],
        ),
        response("第二次。", model="config-model"),
    )
    await integration_agent.send("寻找密道")
    second = integration_data_gateway.narrative_outcomes.get_for_turn(
        "integration_smoke",
        1,
    )
    assert second is not None
    assert second.outcome_code == "critical_failure"
