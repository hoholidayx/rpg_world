from __future__ import annotations

import asyncio
import re

import pytest

from rpg_data import models
from rpg_core.agent.manager import AgentManager
from rpg_core.agent.protocol import StreamEventKind
from rpg_core.context.models import LayerType, Role
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionRoleService,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_send_persists_history_and_turn_metadata(integration_agent, integration_data_gateway):
    reply = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )

    assert reply.stats is not None
    assert reply.stats.total_tokens > 0
    assert reply.text == "config-model response"
    assert [call.model for call in reply.stats.calls] == [
        "status-model",
        "config-model",
    ]
    assert [call.source for call in reply.stats.calls] == [
        "status_outcome_preflight",
        "chat_loop",
    ]
    assert [m.role for m in integration_agent.history] == [Role.USER, Role.ASSISTANT]
    assert [m.turn_id for m in integration_agent.history] == [1, 1]

    rows = integration_data_gateway.messages.list("integration_smoke")
    backup_rows = integration_data_gateway.backup.messages.list("integration_smoke")
    assert len(rows) == 2
    assert [row.turn_id for row in rows] == [1, 1]
    assert [row.seq_in_turn for row in rows] == [1, 2]
    assert [row.id for row in rows] == [message.uid for message in integration_agent.history]
    assert [(row.role, row.content, row.turn_id, row.seq_in_turn) for row in backup_rows] == [
        (row.role, row.content, row.turn_id, row.seq_in_turn) for row in rows
    ]


@pytest.mark.asyncio
async def test_multiple_sends_increment_turn_ids_and_append_history(integration_agent, integration_data_gateway):
    first = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )
    second = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence again."),
        timeout=120,
    )

    assert first.stats is not None and first.stats.total_tokens > 0
    assert second.stats is not None and second.stats.total_tokens > 0
    assert [m.role for m in integration_agent.history] == [
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
        Role.ASSISTANT,
    ]
    assert [m.turn_id for m in integration_agent.history] == [1, 1, 2, 2]

    rows = integration_data_gateway.messages.list("integration_smoke")
    assert len(rows) == 4
    assert [row.turn_id for row in rows] == [1, 1, 2, 2]


@pytest.mark.asyncio
async def test_send_stream_emits_done_event(integration_agent):
    events = []

    async with asyncio.timeout(120):
        async for event in integration_agent.send_stream("Reply in one short sentence."):
            events.append(event)

    assert events
    assert events[-1].kind == StreamEventKind.DONE
    assert events[-1].stats is not None
    assert events[-1].stats.total_tokens > 0


@pytest.mark.asyncio
async def test_send_stream_persists_history_and_turn_metadata(integration_agent, integration_data_gateway):
    events = []

    async with asyncio.timeout(120):
        async for event in integration_agent.send_stream("Reply in one short sentence."):
            events.append(event)

    assert events
    assert events[-1].kind == StreamEventKind.DONE
    assert events[-1].stats is not None
    assert events[-1].stats.total_tokens > 0
    assert integration_agent.history
    assert integration_agent.history[0].role == Role.USER
    assert integration_agent.history[0].turn_id == 1

    rows = integration_data_gateway.messages.list("integration_smoke")
    assert len(rows) >= 1
    assert rows[0].turn_id == 1


@pytest.mark.asyncio
async def test_command_help_and_context_are_available(integration_agent):
    help_result = await asyncio.wait_for(integration_agent.execute_command("/help"), timeout=120)
    context_result = await asyncio.wait_for(integration_agent.execute_command("/context"), timeout=120)
    sessions_result = await asyncio.wait_for(integration_agent.execute_command("/sessions"), timeout=120)

    assert help_result.handled is True
    assert "/clear" in help_result.reply
    assert "/session_switch" in help_result.reply

    assert context_result.handled is True
    assert "Layer" in context_result.reply or "层" in context_result.reply

    assert sessions_result.handled is True
    assert "会话列表" in sessions_result.reply
    assert "integration_smoke" in sessions_result.reply


@pytest.mark.asyncio
async def test_status_tables_and_scene_enter_agent_context(integration_status_agent):
    ctx = integration_status_agent._context_service.build_for_inspection("inspect status")
    user_content = ctx.render_layer(LayerType.USER_MESSAGE)
    status_content = ctx.render_layer(LayerType.STATUS_TABLES)

    assert integration_status_agent._lifecycle.resources.scene_tracker is not None
    assert user_content is not None
    assert "[scene]" in user_content
    assert "位置: 集成测试大厅" in user_content
    assert "在场人物: 测试者" in user_content
    assert "inspect status" in user_content

    assert [table["name"] for table in ctx.status_tables.tables] == ["集成线索"]
    assert status_content is not None
    assert "## 状态表" in status_content
    assert "### 集成线索" in status_content
    assert "运行时表 ID：" in status_content
    assert "用途与更新规则：" in status_content
    assert "状态表已挂载" in status_content
    assert "集成当前场景" not in status_content


@pytest.mark.asyncio
async def test_session_create_and_switch_locator_isolate_history(
    integration_agent,
    integration_data_gateway,
):
    create_result = await asyncio.wait_for(
        integration_agent.execute_command("/session_create alt_session"),
        timeout=120,
    )
    assert create_result.handled is True
    assert "已创建" in create_result.reply
    match = re.search(r"\[会话已创建: ([A-Za-z0-9_]+)\]", create_result.reply)
    assert match is not None
    created_session_id = match.group(1)
    current_session = integration_data_gateway.catalog.get_session("integration_smoke")
    assert current_session is not None
    sessions = integration_data_gateway.catalog.list_sessions(
        str(current_session.workspace_id),
        int(current_session.story_id),
    )
    assert sorted(session.id for session in sessions or []) == sorted([created_session_id, "integration_smoke"])
    role_service = SessionRoleService(integration_data_gateway)
    option = role_service.list_options(created_session_id)[0]
    bound = role_service.bind_player_character(
        created_session_id,
        option.snapshot.character_id,
    )
    assert bound.state.status is PlayerCharacterBindingStatus.BOUND

    first_reply = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )
    assert first_reply.stats is not None
    assert first_reply.stats.total_tokens > 0

    switch_result = await asyncio.wait_for(
        integration_agent.execute_command(f"/session_switch {created_session_id}"),
        timeout=120,
    )
    assert switch_result.handled is True
    assert "已切换" in switch_result.reply
    assert switch_result.active_session == created_session_id
    assert integration_agent.session_id == "integration_smoke"
    assert [m.turn_id for m in integration_agent.history] == [1, 1]

    target_agent = AgentManager.get_or_create(created_session_id)
    second_reply = await asyncio.wait_for(
        target_agent.send("Reply in one short sentence again."),
        timeout=120,
    )
    assert second_reply.stats is not None
    assert second_reply.stats.total_tokens > 0
    assert [m.turn_id for m in target_agent.history] == [1, 1]

    default_rows = integration_data_gateway.messages.list("integration_smoke")
    alt_rows = integration_data_gateway.messages.list(created_session_id)

    assert default_rows[0].turn_id == 1
    assert len(alt_rows) == 2
    assert [row.turn_id for row in alt_rows] == [1, 1]


@pytest.mark.asyncio
async def test_clear_command_empties_history_and_truncates_main_table(integration_agent, integration_data_gateway):
    await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )
    assert integration_agent.history

    clear_result = await asyncio.wait_for(integration_agent.execute_command("/clear"), timeout=120)

    assert clear_result.handled is True
    assert "已清空" in clear_result.reply
    assert integration_agent.history == []
    assert integration_data_gateway.messages.count("integration_smoke") == 0


@pytest.mark.asyncio
async def test_reload_command_preserves_history_and_allows_followup_turn(integration_agent, integration_data_gateway):
    first_reply = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )
    assert first_reply.stats is not None
    before_history = [m.to_dict() for m in integration_agent.history]

    reload_result = await asyncio.wait_for(integration_agent.execute_command("/reload"), timeout=120)

    assert reload_result.handled is True
    assert "已重新加载" in reload_result.reply
    assert [m.to_dict() for m in integration_agent.history] == before_history

    second_reply = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence again."),
        timeout=120,
    )
    assert second_reply.stats is not None
    assert second_reply.stats.total_tokens > 0

    rows = integration_data_gateway.messages.list("integration_smoke")
    assert len(rows) == 4
    assert [row.turn_id for row in rows] == [1, 1, 2, 2]


@pytest.mark.asyncio
async def test_context_inspection_reports_active_history_and_user_message_layer(
    integration_agent,
    integration_data_gateway,
):
    await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )
    history_snapshot = [m.to_dict() for m in integration_agent.history]
    db_snapshot = [
        row.to_message_dict()
        for row in integration_data_gateway.messages.list("integration_smoke")
    ]

    layers = await asyncio.wait_for(
        integration_agent.get_context_info("inspect me"),
        timeout=120,
    )
    markdown = await asyncio.wait_for(
        integration_agent.get_context_markdown("inspect me"),
        timeout=120,
    )

    assert [m.to_dict() for m in integration_agent.history] == history_snapshot
    assert [
        row.to_message_dict()
        for row in integration_data_gateway.messages.list("integration_smoke")
    ] == db_snapshot

    user_layer = next(info for info in layers if info.type == "user_message")
    hot_history_layer = next(info for info in layers if info.type == "hot_history")

    assert user_layer.status == "active"
    assert user_layer.role == Role.USER.value
    assert user_layer.char_count > 0
    assert hot_history_layer.status == "active"
    assert hot_history_layer.role == "mixed"

    assert "上下文概览" in markdown
    assert "分层明细" in markdown
    assert "历史消息" in markdown
    assert "历史轮数" in markdown
    assert "User Message" in markdown
