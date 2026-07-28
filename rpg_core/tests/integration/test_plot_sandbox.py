from __future__ import annotations

import json

import pytest

from commons.scene_time import SceneTime
from rpg_core.rp_modules.plot_scheduler import (
    CreatePlotEventCommand,
    CreatePlotPoolCommand,
    PlotScheduleManagementService,
)
from rpg_data import models
from rpg_data.errors import DataConditionalWriteError
from tests.support.scripted_llm import response, tool_call

pytestmark = pytest.mark.integration


def _seed_plot_events(
    gateway,
    session_id: str,
    *definitions: tuple[str, str],
    cooldown_minutes: int = 0,
):
    session = gateway.sessions.get_session(session_id)
    assert session is not None
    service = PlotScheduleManagementService(gateway.plot_scheduling)
    pool = service.create_pool(
        CreatePlotPoolCommand(
            workspace_id=session.workspace_id,
            story_id=session.story_id,
            name=f"{session_id} 手动注入池",
            selection_mode=models.PLOT_POOL_SEQUENTIAL,
            priority=100,
            cooldown_minutes=cooldown_minutes,
        )
    )
    events = tuple(
        service.create_event(
            CreatePlotEventCommand(
                workspace_id=session.workspace_id,
                story_id=session.story_id,
                pool_id=pool.id,
                title=title,
                directive=directive,
            )
        )
        for title, directive in definitions
    )
    return service, pool, events


def _mark_tool_response(
    event_id: int | None,
    *,
    title: str | None = None,
    directive: str | None = None,
    call_id: str = "plot_mark",
):
    arguments: dict[str, object] = {"event_id": event_id}
    if title is not None:
        arguments["title"] = title
    if directive is not None:
        arguments["directive"] = directive
    return response(
        "",
        model="config-model",
        tool_calls=[
            tool_call(
                "plot_event_mark_next",
                json.dumps(arguments, ensure_ascii=False),
                call_id=call_id,
            )
        ],
        finish_reason="tool_calls",
    )


def _tool_names(call) -> set[str]:  # noqa: ANN001
    return {
        str(schema["function"]["name"])
        for schema in call.tools or []
    }


def _latest_user_content(call) -> str:  # noqa: ANN001
    return str(
        next(
            message["content"]
            for message in reversed(call.messages)
            if message.get("role") == "user"
        )
    )


@pytest.mark.asyncio
async def test_ooc_null_event_id_clears_the_persisted_mark(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
) -> None:
    session_id = "integration_plot_null_clear"
    agent = await integration_agent_factory(session_id)
    _service, _pool, (event,) = _seed_plot_events(
        integration_data_gateway,
        session_id,
        ("待清空事件", "这条指令不应进入世界回合。"),
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        _mark_tool_response(event.id, call_id="mark_before_clear"),
        response("事件已标记。", model="config-model"),
    )
    await agent.send("先标记。", mode="ooc")
    assert integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    ) is not None

    provider.queue_chat(
        _mark_tool_response(None, call_id="clear_with_null"),
        response("标记已清空。", model="config-model"),
    )
    cleared = await agent.send("清空下一轮标记。", mode="ooc")

    result = json.loads(
        str(cleared.tool_records[0].tool_results[0]["content"])
    )
    assert result["ok"] is True
    assert result["pendingForNextNonOocTurn"] is False
    assert result["pendingInjection"] is None
    assert result["replacedOrCleared"]["sourceEventId"] == event.id
    assert integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    ) is None
    assert [
        row.mode
        for row in integration_data_gateway.messages.list(session_id)
    ] == ["ooc", "ooc", "ooc", "ooc"]


@pytest.mark.asyncio
async def test_ooc_mark_is_mode_tagged_and_injected_once_on_next_non_ooc_turn(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
) -> None:
    session_id = "integration_plot_ooc_mark"
    agent = await integration_agent_factory(session_id)
    _service, pool, (event,) = _seed_plot_events(
        integration_data_gateway,
        session_id,
        ("原始钟声", "让远处钟楼敲响一次。"),
        cooldown_minutes=120,
    )
    automatic_anchor = integration_data_gateway.plot_scheduling.append_decisions(
        session_id,
        1,
        (
            models.StagedPlotScheduleDecision(
                source_kind=models.PLOT_SOURCE_POOL,
                source_id=event.id,
                event_id=event.id,
                container_id=pool.id,
                decision_status=models.PLOT_DECISION_TRIGGERED,
                dispatch_mode=models.PLOT_DISPATCH_FORCED,
                selection_origin=models.PLOT_SELECTION_ORIGIN_SCHEDULER,
                scene_time=SceneTime(1, 1, 1, 6),
                event_snapshot={
                    "eventTitle": event.title,
                    "directive": event.directive,
                },
                reason="预置自动池冷却锚点",
            ),
        ),
    )[0]
    provider = scripted_llm_manager.main_provider()
    frozen_title = "临时午夜钟声"
    frozen_directive = "让午夜钟声连续敲响三次，并惊起屋檐上的群鸦。"
    provider.queue_chat(
        _mark_tool_response(
            event.id,
            title=frozen_title,
            directive=frozen_directive,
        ),
        response("已为下一次非 OOC turn 标记该事件。", model="config-model"),
    )

    marked = await agent.send("把钟声安排到下一回合。", mode="ooc")

    assert marked.committed_turn_id == 1
    assert marked.tool_records is not None
    mark_result = json.loads(
        str(marked.tool_records[0].tool_results[0]["content"])
    )
    assert mark_result["ok"] is True
    assert mark_result["pendingInjection"]["eventTitle"] == frozen_title
    assert mark_result["pendingInjection"]["directive"] == frozen_directive
    assert {
        "plot_sandbox_read",
        "plot_event_mark_next",
    } <= _tool_names(provider.calls[0])
    pending = integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    )
    assert pending is not None
    assert pending.event_title == frozen_title
    assert pending.directive == frozen_directive
    assert pending.requested_turn_id == 1
    assert [
        (row.role, row.mode)
        for row in integration_data_gateway.messages.list(session_id)
    ] == [("user", "ooc"), ("assistant", "ooc")]

    provider.queue_chat(
        response("标记仍保留，尚未推进世界。", model="config-model")
    )
    await agent.send("先只讨论一下这个安排。", mode="ooc")

    still_pending = (
        integration_data_gateway.plot_scheduling.get_pending_injection(
            session_id
        )
    )
    assert still_pending == pending
    assert [
        row.mode
        for row in integration_data_gateway.messages.list(session_id)
    ] == ["ooc", "ooc", "ooc", "ooc"]

    provider.queue_chat(response("钟声与群鸦同时惊动了街巷。", model="config-model"))
    advanced = await agent.send("我推开窗观察街道。", mode="ic")

    assert advanced.committed_turn_id == 3
    world_call = provider.calls[-1]
    runtime_input = _latest_user_content(world_call)
    assert "[engine_plot_directive]" in runtime_input
    assert frozen_title in runtime_input
    assert frozen_directive in runtime_input
    assert integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    ) is None
    decisions = integration_data_gateway.plot_scheduling.list_session_decisions(
        session_id
    )
    assert len(decisions) == 2
    manual = next(
        item
        for item in decisions
        if item.selection_origin == models.PLOT_SELECTION_ORIGIN_MANUAL
    )
    assert manual.event_id == event.id
    assert manual.scene_time is None
    anchors = (
        integration_data_gateway.plot_scheduling
        .list_latest_session_decisions_by_container(
            session_id,
            source_kind=models.PLOT_SOURCE_POOL,
            decision_statuses={models.PLOT_DECISION_TRIGGERED},
            selection_origins={models.PLOT_SELECTION_ORIGIN_SCHEDULER},
        )
    )
    assert [item.id for item in anchors] == [automatic_anchor.id]
    rows = integration_data_gateway.messages.list(session_id)
    assert [row.mode for row in rows] == [
        "ooc",
        "ooc",
        "ooc",
        "ooc",
        "ic",
        "ic",
    ]
    assert frozen_directive not in rows[-2].content
    assert "[engine_plot_directive]" not in rows[-2].content


@pytest.mark.asyncio
async def test_frozen_mark_survives_source_event_deletion_before_consumption(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
) -> None:
    session_id = "integration_plot_orphan_mark"
    agent = await integration_agent_factory(session_id)
    service, _pool, (event,) = _seed_plot_events(
        integration_data_gateway,
        session_id,
        ("将被删除的定义", "原始指令不会被使用。"),
    )
    provider = scripted_llm_manager.main_provider()
    frozen_title = "孤儿快照事件"
    frozen_directive = "让一封没有署名的蓝色信件从门缝滑入。"
    provider.queue_chat(
        _mark_tool_response(
            event.id,
            title=frozen_title,
            directive=frozen_directive,
        ),
        response("快照已冻结。", model="config-model"),
    )
    await agent.send("冻结后等待下一轮。", mode="ooc")

    session = integration_data_gateway.sessions.get_session(session_id)
    assert session is not None
    service.delete_event(session.workspace_id, session.story_id, event.id)
    assert (
        integration_data_gateway.plot_scheduling.get_event(
            session.story_id,
            event.id,
        )
        is None
    )
    assert integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    ) is not None

    provider.queue_chat(response("蓝色信件滑进了房间。", model="config-model"))
    await agent.send("我听见门外传来轻响。")

    runtime_input = _latest_user_content(provider.calls[-1])
    assert frozen_title in runtime_input
    assert frozen_directive in runtime_input
    assert integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    ) is None
    decision = integration_data_gateway.plot_scheduling.list_session_decisions(
        session_id
    )[0]
    assert decision.event_id == event.id
    assert decision.event_snapshot["eventTitle"] == frozen_title
    assert decision.event_snapshot["directive"] == frozen_directive


@pytest.mark.asyncio
async def test_provider_failures_do_not_persist_mark_or_consume_pending_snapshot(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
) -> None:
    session_id = "integration_plot_failure"
    agent = await integration_agent_factory(session_id)
    _service, _pool, (event,) = _seed_plot_events(
        integration_data_gateway,
        session_id,
        ("失败保护事件", "让庭院中的灯依次熄灭。"),
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        _mark_tool_response(event.id),
        RuntimeError("provider failed after mark"),
    )

    with pytest.raises(RuntimeError, match="provider failed after mark"):
        await agent.send("标记事件，但本轮随后失败。", mode="ooc")

    assert integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    ) is None
    assert integration_data_gateway.messages.list(session_id) == []
    assert integration_data_gateway.backup.messages.list(session_id) == []

    provider.queue_chat(
        _mark_tool_response(event.id, call_id="plot_mark_retry"),
        response("重试标记成功。", model="config-model"),
    )
    await agent.send("重新标记这个事件。", mode="ooc")
    pending = integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    )
    assert pending is not None
    provider.queue_chat(RuntimeError("target world turn failed"))

    with pytest.raises(RuntimeError, match="target world turn failed"):
        await agent.send("尝试推进，但生成失败。")

    assert (
        integration_data_gateway.plot_scheduling.get_pending_injection(
            session_id
        )
        == pending
    )
    assert integration_data_gateway.plot_scheduling.list_session_decisions(
        session_id
    ) == []
    assert [
        (row.turn_id, row.mode)
        for row in integration_data_gateway.messages.list(session_id)
    ] == [(1, "ooc"), (1, "ooc")]
    assert integration_data_gateway.backup.messages.count(session_id) == 2


@pytest.mark.asyncio
async def test_gm_turn_consumes_old_snapshot_and_marks_a_new_one(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
) -> None:
    session_id = "integration_plot_gm_replace"
    agent = await integration_agent_factory(session_id)
    _service, _pool, (first_event, second_event) = _seed_plot_events(
        integration_data_gateway,
        session_id,
        ("旧事件", "让旧事件在本轮发生。"),
        ("新事件", "让新事件在下一轮发生。"),
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        _mark_tool_response(first_event.id, call_id="mark_old"),
        response("旧事件已标记。", model="config-model"),
    )
    await agent.send("先标记旧事件。", mode="ooc")
    old_pending = (
        integration_data_gateway.plot_scheduling.get_pending_injection(
            session_id
        )
    )
    assert old_pending is not None

    replacement_title = "下一轮的新事件快照"
    replacement_directive = "让新事件以临时调整后的内容发生。"
    provider.queue_chat(
        _mark_tool_response(
            second_event.id,
            title=replacement_title,
            directive=replacement_directive,
            call_id="mark_new",
        ),
        response("旧事件已发生，新事件已排入下一轮。", model="config-model"),
    )
    gm_reply = await agent.send("推进旧事件，并安排之后的新事件。", mode="gm")

    assert gm_reply.committed_turn_id == 2
    gm_initial_call = provider.calls[-2]
    assert "让旧事件在本轮发生。" in _latest_user_content(gm_initial_call)
    assert {
        "plot_sandbox_read",
        "plot_event_mark_next",
    } <= _tool_names(gm_initial_call)
    decisions = integration_data_gateway.plot_scheduling.list_session_decisions(
        session_id
    )
    assert len(decisions) == 1
    assert decisions[0].event_id == first_event.id
    assert decisions[0].selection_origin == models.PLOT_SELECTION_ORIGIN_MANUAL
    pending = integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    )
    assert pending is not None
    assert pending.version == old_pending.version + 1
    assert pending.source_event_id == second_event.id
    assert pending.event_title == replacement_title
    assert pending.directive == replacement_directive
    assert pending.requested_turn_id == 2
    assert [
        row.mode
        for row in integration_data_gateway.messages.list(session_id)
    ] == ["ooc", "ooc", "gm", "gm"]


@pytest.mark.asyncio
async def test_pending_cas_conflict_rolls_back_target_messages_and_decision(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
) -> None:
    session_id = "integration_plot_pending_cas"
    agent = await integration_agent_factory(session_id)
    _service, _pool, (event,) = _seed_plot_events(
        integration_data_gateway,
        session_id,
        ("并发事件", "让并发事件按原快照发生。"),
    )
    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        _mark_tool_response(event.id),
        response("初始快照已标记。", model="config-model"),
    )
    await agent.send("标记并发测试事件。", mode="ooc")
    base = integration_data_gateway.plot_scheduling.get_pending_injection(
        session_id
    )
    assert base is not None

    def concurrent_replace(messages, tools):  # noqa: ANN001, ANN202
        del messages, tools
        snapshot = dict(base.event_snapshot)
        snapshot.update({
            "eventTitle": "并发替换快照",
            "directive": "这是并发写入后应保留的快照。",
        })
        integration_data_gateway.plot_scheduling.replace_pending_injection(
            session_id,
            expected_version=base.version,
            values=models.PendingPlotInjectionWrite(
                story_id=base.story_id,
                source_event_id=base.source_event_id,
                source_event_version=base.source_event_version,
                source_pool_id=base.source_pool_id,
                source_pool_name=base.source_pool_name,
                event_title="并发替换快照",
                directive="这是并发写入后应保留的快照。",
                event_snapshot=snapshot,
                requested_turn_id=base.requested_turn_id,
            ),
        )
        return response("这个回复不得提交。", model="config-model")

    provider.queue_chat(concurrent_replace)

    with pytest.raises(DataConditionalWriteError):
        await agent.send("触发旧快照的 CAS 冲突。")

    rows = integration_data_gateway.messages.list(session_id)
    backup = integration_data_gateway.backup.messages.list(session_id)
    assert [(row.turn_id, row.mode) for row in rows] == [
        (1, "ooc"),
        (1, "ooc"),
    ]
    assert [(row.turn_id, row.mode) for row in backup] == [
        (1, "ooc"),
        (1, "ooc"),
    ]
    assert integration_data_gateway.plot_scheduling.list_session_decisions(
        session_id
    ) == []
    concurrent = (
        integration_data_gateway.plot_scheduling.get_pending_injection(
            session_id
        )
    )
    assert concurrent is not None
    assert concurrent.version == base.version + 1
    assert concurrent.event_title == "并发替换快照"
    assert concurrent.directive == "这是并发写入后应保留的快照。"
