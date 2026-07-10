from __future__ import annotations

import asyncio

import pytest

import rpg_core.agent.agent as agent_module
from llm_service.types import ProviderChunk
from rpg_core.agent.agent_types import StreamEventKind, TurnCancelStatus
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
        yield agent_module.AgentStreamEvent(kind=StreamEventKind.ROUND_START)

    monkeypatch.setattr(agent_module, "run_chat_loop_stream", incomplete_loop)

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
    table = integration_status_agent._status_mgr.list_context_tables()[0]
    table_id = int(table["id"])
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
async def test_status_commit_failure_rolls_back_messages_backup_and_document(
    integration_status_agent,
    integration_data_gateway,
    scripted_llm_manager,
    monkeypatch,
):
    table = integration_status_agent._status_mgr.list_context_tables()[0]
    table_id = int(table["id"])
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

    monkeypatch.setattr(integration_status_agent._status_mgr, "save_table_document", fail_save)

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
        integration_agent._memory_sub_agent,
        "maybe_auto_extract",
        fail_after_commit,
    )

    reply = await integration_agent.send("commit first")

    assert reply.text == "config-model response"
    assert integration_data_gateway.messages.count("integration_smoke") == 2
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 2


@pytest.mark.asyncio
async def test_main_agent_tool_round_trip_uses_real_registry_but_persists_only_final_messages(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        response(
            "",
            model="config-model",
            tool_calls=[tool_call("rp_dice_roll", '{"expression":"1d2"}')],
        ),
        response("骰子已经落定。", model="config-model"),
    )

    reply = await integration_agent.send("掷一个骰子")

    assert reply.text == "骰子已经落定。"
    assert reply.tool_records and len(reply.tool_records) == 1
    assert len(provider.calls) == 2
    second_messages = provider.calls[1].messages
    assert any(
        message.get("role") == "tool" and "骰子结果" in message.get("content", "")
        for message in second_messages
    )
    rows = integration_data_gateway.messages.list("integration_smoke")
    assert [(row.role, row.content) for row in rows] == [
        ("user", "掷一个骰子"),
        ("assistant", "骰子已经落定。"),
    ]
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 2
