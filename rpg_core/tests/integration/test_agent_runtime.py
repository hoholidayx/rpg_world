from __future__ import annotations

import asyncio

import pytest

from commons.errors import MainContextWindowThresholdExceededError
from llm_service.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_MEMORY_SUB_AGENT_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
)
from llm_service.types import ProviderChunk
from rpg_core.agent.agent_types import StreamEventKind
from rpg_core.main_llm import MainLLMSelectionService
from rpg_core.tests.integration.scripted_llm import (
    CONFIG_PROVIDER_KEY,
    SESSION_PROVIDER_KEY,
    STORY_PROVIDER_KEY,
    response,
    tool_call,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_role_guard_bind_and_first_message_are_end_to_end_and_idempotent(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "integration_role"
    first_message = "你在测试大厅醒来。"
    agent = await integration_agent_factory(
        session_id,
        bind_role=False,
        first_message=first_message,
    )

    blocked = await agent.send("在吗？")

    assert "请选择你要扮演的角色" in blocked.text
    assert scripted_llm_manager.main_provider().calls == []
    assert integration_data_gateway.messages.count(session_id) == 0
    assert integration_data_gateway.backup.messages.count(session_id) == 0

    bound = await agent.execute_command("/role_bind 1")
    rebound = await agent.execute_command("/role_bind 1")

    assert bound.handled is True and bound.reply == first_message
    assert rebound.handled is True and "已切换扮演角色" in rebound.reply
    first_rows = integration_data_gateway.messages.list(session_id)
    first_backup = integration_data_gateway.backup.messages.list(session_id)
    assert [(row.role, row.content, row.turn_id, row.seq_in_turn) for row in first_rows] == [
        ("assistant", first_message, 1, 1),
    ]
    assert [(row.role, row.content) for row in first_backup] == [("assistant", first_message)]

    reply = await agent.send("现在开始")

    assert reply.text == "config-model response"
    rows = integration_data_gateway.messages.list(session_id)
    assert [(row.turn_id, row.seq_in_turn) for row in rows] == [(1, 1), (2, 1), (2, 2)]
    assert integration_data_gateway.backup.messages.count(session_id) == 3


@pytest.mark.asyncio
async def test_clear_removes_mutable_history_but_preserves_append_only_backup(
    integration_agent,
    integration_data_gateway,
):
    await integration_agent.send("before clear")
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 2

    result = await integration_agent.execute_command("/clear")

    assert result.handled is True
    assert integration_agent.history == []
    assert integration_data_gateway.messages.count("integration_smoke") == 0
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 2

    await integration_agent.send("after clear")
    assert [row.turn_id for row in integration_data_gateway.messages.list("integration_smoke")] == [1, 1]
    assert integration_data_gateway.backup.messages.count("integration_smoke") == 4


@pytest.mark.asyncio
async def test_main_llm_runtime_priority_context_window_and_subagent_route_independence(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "integration_llm_priority"
    agent = await integration_agent_factory(session_id, with_status=True)
    session = integration_data_gateway.catalog.get_session(session_id)
    story = integration_data_gateway.catalog.get_session_story(session_id)
    assert session is not None and story is not None
    selection = MainLLMSelectionService(integration_data_gateway)

    default_reply = await agent.send("config")
    story_selected = selection.set_story_provider_key(
        str(story.workspace_id),
        int(story.id),
        STORY_PROVIDER_KEY,
    )
    story_reply = await agent.send("story")
    session_selected = selection.set_session_provider_key(session_id, SESSION_PROVIDER_KEY)
    session_reply = await agent.send("session")
    preview = await agent.get_context_payload()
    session_cleared = selection.set_session_provider_key(session_id, None)
    fallback_reply = await agent.send("fallback")

    assert default_reply.text == "config-model response"
    assert story_selected is not None and story_selected.effective_source == "story"
    assert story_reply.text == "story-model response"
    assert session_selected is not None and session_selected.effective_source == "session"
    assert session_reply.text == "session-model response"
    assert preview["usageEstimate"]["contextLimit"] == 8_192
    assert session_cleared is not None and session_cleared.effective_source == "story"
    assert fallback_reply.text == "story-model response"

    main_routes = [
        call.provider_key
        for call in scripted_llm_manager.calls
        if call.biz_key == AGENT_MAIN_BIZ_KEY
    ]
    assert main_routes == [
        CONFIG_PROVIDER_KEY,
        STORY_PROVIDER_KEY,
        SESSION_PROVIDER_KEY,
        STORY_PROVIDER_KEY,
    ]
    assert len(scripted_llm_manager.status.calls) == 4
    assert scripted_llm_manager.status.get_default_model() == "status-model"
    assert any(
        call.biz_key == AGENT_STATUS_SUB_AGENT_BIZ_KEY and call.provider_key is None
        for call in scripted_llm_manager.calls
    )


@pytest.mark.asyncio
async def test_provider_switch_during_active_stream_only_applies_to_next_turn(
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
            ProviderChunk(content="old provider reply"),
            ProviderChunk(
                finish_reason="stop",
                model="config-model",
            ),
        )

    scripted_llm_manager.main_provider().queue_stream(gated_stream)
    events = []

    async def consume() -> None:
        async for event in integration_agent.send_stream("first", request_id="req_switch"):
            events.append(event)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=2)
    selection = MainLLMSelectionService(integration_data_gateway)
    updated = selection.set_session_provider_key("integration_smoke", SESSION_PROVIDER_KEY)
    assert updated is not None
    release.set()
    await asyncio.wait_for(task, timeout=2)

    assert events[-1].kind == StreamEventKind.DONE
    assert events[-1].content == "old provider reply"
    assert events[-1].model == "config-model"

    next_reply = await integration_agent.send("second")

    assert next_reply.text == "session-model response"
    rows = integration_data_gateway.messages.list("integration_smoke")
    assert [(row.turn_id, row.content) for row in rows] == [
        (1, "first"),
        (1, "old provider reply"),
        (2, "second"),
        (2, "session-model response"),
    ]


@pytest.mark.asyncio
async def test_story_memory_extraction_runs_after_commit_and_marks_message_rows(
    integration_agent_factory,
    integration_data_gateway,
    integration_settings,
    scripted_llm_manager,
    monkeypatch,
):
    monkeypatch.setattr(
        type(integration_settings),
        "memory_story_trigger_rounds",
        property(lambda self: 1),
    )
    session_id = "integration_story_memory"
    agent = await integration_agent_factory(session_id)
    scripted_llm_manager.memory.queue_chat(
        response(
            "",
            model="memory-model",
            tool_calls=[
                tool_call(
                    "extract_story_details",
                    '{"story_details":["测试者在大厅发现了一枚银色钥匙。"]}',
                )
            ],
        )
    )

    reply = await agent.send("我捡起银色钥匙")

    assert reply.text == "config-model response"
    memories = integration_data_gateway.story_memory.list(session_id)
    assert [item.text for item in memories] == ["测试者在大厅发现了一枚银色钥匙。"]
    rows = integration_data_gateway.messages.list(session_id)
    assert rows and all(row.story_memory_processed for row in rows)
    assert any(
        call.biz_key == AGENT_MEMORY_SUB_AGENT_BIZ_KEY and call.provider_key is None
        for call in scripted_llm_manager.calls
    )


@pytest.mark.asyncio
async def test_turn_mode_style_snapshot_and_ooc_policy_are_end_to_end(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "integration_composer"
    agent = await integration_agent_factory(session_id, with_status=True)
    session = integration_data_gateway.catalog.get_session(session_id)
    assert session is not None
    style = integration_data_gateway.session_composer.create_style(
        session.workspace_id,
        name="集成测试风格",
        prompt="COMPOSER_STYLE_PROMPT",
        sort_order=90,
    )
    assert style is not None
    mount = integration_data_gateway.session_composer.mount_story_style(
        session.workspace_id,
        session.story_id,
        style.id,
    )
    assert mount is not None

    preview = await agent.get_context_payload(mode="gm", narrative_style_id=style.id)
    assert any(
        "COMPOSER_STYLE_PROMPT" in str(message.get("content") or "")
        for message in preview["messages"]
    )

    status_calls_before = len(scripted_llm_manager.status.calls)
    ooc_reply = await agent.send(
        "解释当前规则",
        mode="ooc",
        narrative_style_id=style.id,
    )
    ooc_call = scripted_llm_manager.main_provider().calls[-1]
    ooc_content = "\n".join(str(message.get("content") or "") for message in ooc_call.messages)
    ooc_tool_names = {
        str(schema.get("function", {}).get("name", ""))
        for schema in (ooc_call.tools or [])
    }
    assert ooc_reply.committed_turn_id == 1
    assert len(scripted_llm_manager.status.calls) == status_calls_before
    assert "COMPOSER_STYLE_PROMPT" not in ooc_content
    assert "硬性边界：本轮是场外讨论" in ooc_content
    assert not ({"rp_story_outcome", "status_table_set_values", "write_file"} & ooc_tool_names)
    assert not any(name.startswith("scene_") for name in ooc_tool_names)

    gm_reply = await agent.send("推进场景", mode="gm", narrative_style_id=style.id)
    gm_call = scripted_llm_manager.main_provider().calls[-1]
    gm_content = "\n".join(str(message.get("content") or "") for message in gm_call.messages)
    assert gm_reply.committed_turn_id == 2
    assert len(scripted_llm_manager.status.calls) == status_calls_before + 1
    assert "COMPOSER_STYLE_PROMPT" in gm_content
    rows = integration_data_gateway.messages.list(session_id)
    assert [row.mode for row in rows] == ["ooc", "ooc", "gm", "gm"]
    assert all(row.summary_processed and row.summary_batch_id is None for row in rows[:2])
    assert all(row.story_memory_processed for row in rows[:2])


@pytest.mark.asyncio
async def test_main_context_and_preview_filter_summary_processed_rows_only(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "integration_context_projection"
    agent = await integration_agent_factory(session_id)

    await agent.send("第一轮用户输入")
    before = await agent.get_context_payload()
    first_rows = integration_data_gateway.messages.list(session_id)
    first_user = next(row for row in first_rows if row.role == "user")
    integration_data_gateway.messages.mark_summary_processed(
        session_id,
        [first_user.id],
        batch_id=999,
    )

    after = await agent.get_context_payload()
    after_contents = [str(message["content"]) for message in after["messages"]]

    assert [row.content for row in integration_data_gateway.messages.list(session_id)] == [
        "第一轮用户输入",
        "config-model response",
    ]
    assert all("第一轮用户输入" not in content for content in after_contents)
    assert "config-model response" in after_contents
    assert after["usageEstimate"]["usedTokens"] < before["usageEstimate"]["usedTokens"]
    assert after["usageEstimate"]["usedTokens"] == after["totals"]["tokenCount"]

    await agent.send("第二轮用户输入")
    send_call = scripted_llm_manager.main_provider().calls[-1]
    send_contents = [str(message.get("content") or "") for message in send_call.messages]
    assert all("第一轮用户输入" not in content for content in send_contents)
    assert "config-model response" in send_contents
    assert any("第二轮用户输入" in content for content in send_contents)

    second_user = next(
        row
        for row in integration_data_gateway.messages.list(session_id)
        if row.role == "user" and row.content == "第二轮用户输入"
    )
    integration_data_gateway.messages.mark_summary_processed(
        session_id,
        [second_user.id],
        batch_id=1000,
    )

    events = [event async for event in agent.send_stream("第三轮用户输入")]
    stream_call = scripted_llm_manager.main_provider().calls[-1]
    stream_contents = [str(message.get("content") or "") for message in stream_call.messages]
    assert events[-1].kind == StreamEventKind.DONE
    assert stream_call.stream is True
    assert all("第一轮用户输入" not in content for content in stream_contents)
    assert all("第二轮用户输入" not in content for content in stream_contents)
    assert any("第三轮用户输入" in content for content in stream_contents)


@pytest.mark.asyncio
async def test_context_threshold_uses_filtered_current_context_and_excludes_new_input(
    integration_agent_factory,
    integration_data_gateway,
    integration_settings,
    scripted_llm_manager,
    monkeypatch,
):
    session_id = "integration_context_threshold"
    agent = await integration_agent_factory(session_id)
    await agent.send("第一轮用于门禁的用户输入")
    before = await agent.get_context_payload()
    used_tokens = int(before["usageEstimate"]["usedTokens"])
    context_limit = int(before["usageEstimate"]["contextLimit"])
    threshold_ratio = used_tokens / context_limit
    monkeypatch.setattr(
        type(integration_settings),
        "context_window_reject_threshold_ratio",
        property(lambda self: threshold_ratio),
    )
    main_call_count = len(scripted_llm_manager.main_provider().calls)

    with pytest.raises(MainContextWindowThresholdExceededError):
        await agent.send("这条正文不应写入历史")

    assert len(scripted_llm_manager.main_provider().calls) == main_call_count
    assert all(
        row.content != "这条正文不应写入历史"
        for row in integration_data_gateway.messages.list(session_id)
    )

    first_user = next(
        row
        for row in integration_data_gateway.messages.list(session_id)
        if row.role == "user"
    )
    integration_data_gateway.messages.mark_summary_processed(
        session_id,
        [first_user.id],
        batch_id=999,
    )
    after = await agent.get_context_payload()
    assert int(after["usageEstimate"]["usedTokens"]) < used_tokens

    reply = await agent.send("x" * 10_000)

    assert reply.text == "config-model response"


@pytest.mark.asyncio
async def test_summary_compression_writes_batches_and_flags_without_truncating_history(
    integration_agent_factory,
    integration_data_gateway,
    integration_settings,
    scripted_llm_manager,
    monkeypatch,
):
    settings_type = type(integration_settings)
    monkeypatch.setattr(settings_type, "memory_compression_enabled", property(lambda self: True))
    monkeypatch.setattr(settings_type, "memory_keep_rounds", property(lambda self: 1))
    monkeypatch.setattr(settings_type, "memory_compress_batch_size", property(lambda self: 1))
    session_id = "integration_summary"
    agent = await integration_agent_factory(session_id)
    scripted_llm_manager.memory.queue_chat(
        response(
            "",
            model="memory-model",
            tool_calls=[
                tool_call(
                    "generate_batch_summary",
                    '{"title":"第一批","summary_text":"第一轮摘要",'
                    '"time":"第一天","location":"大厅","characters":["测试者"]}',
                )
            ],
        ),
        response(
            "",
            model="memory-model",
            tool_calls=[
                tool_call(
                    "generate_batch_summary",
                    '{"title":"第二批","summary_text":"第二轮摘要",'
                    '"time":"第二天","location":"门厅","characters":["测试者"]}',
                )
            ],
        ),
        response(
            "",
            model="memory-model",
            tool_calls=[
                tool_call(
                    "generate_overall_summary",
                    '{"title":"总览","summary_text":"两轮整体摘要","key_events":["发现线索"]}',
                )
            ],
        ),
    )

    await agent.send("第一轮")
    await agent.send("第二轮")
    await agent.send("第三轮")

    rows = integration_data_gateway.messages.list(session_id)
    assert len(rows) == 6
    assert [row.summary_processed for row in rows] == [True, True, True, True, False, False]
    assert len(agent.history) == 6
    runtime_dir = integration_data_gateway.catalog.get_session_runtime_dir(session_id)
    summary_dir = runtime_dir / "summaries"
    batch_files = sorted(path.name for path in summary_dir.glob("*.md") if path.name != "overall.md")
    assert len(batch_files) == 2
    assert (summary_dir / "overall.md").is_file()
