from __future__ import annotations

import asyncio
import json

import pytest

from rpg_world.rpg_core.agent.agent_types import StreamEventKind
from rpg_world.rpg_core.context.rpg_context import Role
from rpg_world.rpg_core.session.manager import SessionManager

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_send_persists_history_and_turn_metadata(integration_agent, integration_session_dir):
    reply = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )

    assert reply.stats is not None
    assert reply.stats.total_tokens > 0
    assert [m.role for m in integration_agent.history] == [Role.USER, Role.ASSISTANT]
    assert [m.turn_id for m in integration_agent.history] == [1, 1]

    history_path = integration_session_dir / "history.jsonl"
    meta_path = integration_session_dir / "session.json"

    history_rows = history_path.read_text(encoding="utf-8").strip().splitlines()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert len(history_rows) == 2
    assert json.loads(history_rows[0])["turn_id"] == 1
    assert json.loads(history_rows[1])["turn_id"] == 1
    assert meta["next_turn_id"] == 2


@pytest.mark.asyncio
async def test_multiple_sends_increment_turn_ids_and_append_history(integration_agent, integration_session_dir):
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

    history_path = integration_session_dir / "history.jsonl"
    meta_path = integration_session_dir / "session.json"

    history_rows = history_path.read_text(encoding="utf-8").strip().splitlines()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert len(history_rows) == 4
    assert [json.loads(row)["turn_id"] for row in history_rows] == [1, 1, 2, 2]
    assert meta["next_turn_id"] == 3


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
async def test_send_stream_persists_history_and_turn_metadata(integration_agent, integration_session_dir):
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

    history_path = integration_session_dir / "history.jsonl"
    meta_path = integration_session_dir / "session.json"

    history_rows = history_path.read_text(encoding="utf-8").strip().splitlines()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert len(history_rows) >= 1
    assert json.loads(history_rows[0])["turn_id"] == 1
    assert meta["next_turn_id"] == 2


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
async def test_session_create_and_switch_isolate_history(integration_agent, integration_session_dir):
    create_result = await asyncio.wait_for(
        integration_agent.execute_command("/session_create alt_session"),
        timeout=120,
    )
    assert create_result.handled is True
    assert "已创建" in create_result.reply
    assert SessionManager.list_sessions(integration_agent._workspace) == ["alt_session", "integration_smoke"]

    first_reply = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )
    assert first_reply.stats is not None
    assert first_reply.stats.total_tokens > 0

    switch_result = await asyncio.wait_for(
        integration_agent.execute_command("/session_switch alt_session"),
        timeout=120,
    )
    assert switch_result.handled is True
    assert "已切换" in switch_result.reply
    assert integration_agent._session_id == "alt_session"
    assert integration_agent.history == []

    second_reply = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence again."),
        timeout=120,
    )
    assert second_reply.stats is not None
    assert second_reply.stats.total_tokens > 0
    assert [m.turn_id for m in integration_agent.history] == [1, 1]

    default_history = json.loads((integration_session_dir / "history.jsonl").read_text(encoding="utf-8").splitlines()[0])
    alt_session_dir = integration_agent._session._history_path().parent
    alt_rows = (alt_session_dir / "history.jsonl").read_text(encoding="utf-8").strip().splitlines()

    assert default_history["turn_id"] == 1
    assert len(alt_rows) == 2
    assert [json.loads(row)["turn_id"] for row in alt_rows] == [1, 1]


@pytest.mark.asyncio
async def test_clear_command_empties_history_and_truncates_disk(integration_agent, integration_session_dir):
    await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )
    assert integration_agent.history

    clear_result = await asyncio.wait_for(integration_agent.execute_command("/clear"), timeout=120)

    assert clear_result.handled is True
    assert "已清空" in clear_result.reply
    assert integration_agent.history == []
    assert (integration_session_dir / "history.jsonl").read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_reload_command_preserves_history_and_allows_followup_turn(integration_agent, integration_session_dir):
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

    history_rows = (integration_session_dir / "history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(history_rows) == 4
    assert [json.loads(row)["turn_id"] for row in history_rows] == [1, 1, 2, 2]


@pytest.mark.asyncio
async def test_single_turn_without_record_history_rolls_back_history_but_advances_turn_counter(
    integration_agent,
    integration_session_dir,
):
    reply = await asyncio.wait_for(
        integration_agent.single_turn("Reply in one short sentence.", record_history=False),
        timeout=120,
    )

    assert reply.stats is not None
    assert reply.stats.total_tokens > 0
    assert integration_agent.history == []

    history_path = integration_session_dir / "history.jsonl"
    meta_path = integration_session_dir / "session.json"

    history_text = history_path.read_text(encoding="utf-8") if history_path.exists() else ""
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # record_history=False 会回滚可见历史，不会把这次 turn 持久化到磁盘，
    # 但 session 内部的 turn 分配会在后续真实 send() 时继续向前推进。
    assert history_text == ""
    assert meta["next_turn_id"] == 1

    followup = await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence again."),
        timeout=120,
    )
    assert followup.stats is not None
    assert followup.stats.total_tokens > 0
    assert [m.turn_id for m in integration_agent.history] == [2, 2]

    history_rows = history_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(history_rows) == 2
    assert [json.loads(row)["turn_id"] for row in history_rows] == [2, 2]
    meta_after = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta_after["next_turn_id"] == 3


@pytest.mark.asyncio
async def test_context_inspection_reports_active_history_and_user_message_layer(
    integration_agent,
    integration_session_dir,  # noqa: ARG001
):
    await asyncio.wait_for(
        integration_agent.send("Reply in one short sentence."),
        timeout=120,
    )
    history_snapshot = [m.to_dict() for m in integration_agent.history]
    history_path = integration_session_dir / "history.jsonl"
    disk_snapshot = history_path.read_text(encoding="utf-8")

    layers = await asyncio.wait_for(
        integration_agent.get_context_info("inspect me"),
        timeout=120,
    )
    markdown = await asyncio.wait_for(
        integration_agent.get_context_markdown("inspect me"),
        timeout=120,
    )

    assert [m.to_dict() for m in integration_agent.history] == history_snapshot
    assert history_path.read_text(encoding="utf-8") == disk_snapshot

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
