from __future__ import annotations

import asyncio

import pytest

from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_PLOT_SCHEDULER_BIZ_KEY,
)
from llm_client.manager import LLMClientManager
from rpg_core.rp_modules.plot_scheduler import PlotScheduleManagementService
from rpg_core.rp_modules.plot_scheduler.tools import (
    PLOT_EVENT_MARK_NEXT_TOOL_NAME,
    PLOT_SANDBOX_READ_TOOL_NAME,
)
from rpg_data import models
from tests.support.live_agent import (
    DEMO_PLAYER_CHARACTER_NAME,
    LiveDemoHarness,
    ToolInvocation,
    main_tool_call_names,
    main_tool_invocations,
    status_snapshot,
)
from tests.support.plot_execution_verifier import verify_plot_execution

pytestmark = [pytest.mark.integration, pytest.mark.live_llm]

_PLOT_SUFFIX_OPEN = "[engine_plot_directive]"
_PLOT_SUFFIX_CLOSE = "[/engine_plot_directive]"


def _demo_plot_event(
    gateway,
    harness: LiveDemoHarness,
    title: str,
):
    service = PlotScheduleManagementService(gateway.plot_scheduling)
    schedule = service.get_story_schedule(
        harness.workspace_id,
        harness.story_id,
    )
    assert schedule is not None
    return next(event for event in schedule.events if event.title == title)


def _read_result_contains_event(
    invocation: ToolInvocation,
    event_id: int,
) -> bool:
    payload = invocation.result
    assert isinstance(payload, dict)
    if payload.get("resource") == "event":
        if payload.get("view") == "detail":
            return payload.get("item", {}).get("id") == event_id
        return any(
            item.get("id") == event_id
            for item in payload.get("items", [])
        )
    if payload.get("resource") == "pool" and payload.get("view") == "detail":
        return any(
            item.get("id") == event_id
            for item in payload.get("item", {}).get("events", [])
        )
    return False


@pytest.mark.asyncio
async def test_live_llm_reads_plot_event_with_sandbox_tool(
    live_demo_harness,
    integration_data_gateway,
) -> None:
    harness = live_demo_harness
    title = "无署名纸鹤送达"
    event = _demo_plot_event(
        integration_data_gateway,
        harness,
        title,
    )

    reply = await asyncio.wait_for(
        harness.agent.send(
            (
                "我先做一下场外的剧情规划，不推进当前故事。"
                f"请查看剧情沙盘里“{title}”这个事件的完整设置，"
                "告诉我它目前的剧情指令。只查看，不要更改任何安排。"
            ),
            mode="ooc",
        ),
        timeout=180,
    )

    matching_calls = [
        invocation
        for invocation in main_tool_invocations(
            reply,
            PLOT_SANDBOX_READ_TOOL_NAME,
        )
        if invocation.arguments.get("resource") == "event"
        and invocation.arguments.get("id") == event.id
    ]
    assert matching_calls, "live LLM did not read the requested Plot event"
    payload = matching_calls[-1].result
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert payload["resource"] == "event"
    assert payload["view"] == "detail"
    assert payload["item"]["id"] == event.id
    assert payload["item"]["title"] == title
    assert payload["item"]["directive"] == event.directive
    assert not main_tool_invocations(reply, PLOT_EVENT_MARK_NEXT_TOOL_NAME)
    assert (
        integration_data_gateway.plot_scheduling.get_pending_injection(
            harness.session_id
        )
        is None
    )
    assert reply.stats is not None
    assert reply.stats.total_tokens > 0


@pytest.mark.asyncio
async def test_live_llm_marks_and_executes_plot_event_on_next_world_turn(
    live_demo_harness,
    integration_data_gateway,
) -> None:
    harness = live_demo_harness
    original_title = "灰袍监察员经过"
    event = _demo_plot_event(
        integration_data_gateway,
        harness,
        original_title,
    )
    schedule_service = PlotScheduleManagementService(
        integration_data_gateway.plot_scheduling
    )
    decisions_before = schedule_service.list_session_decisions(
        harness.session_id
    )
    assert any(
        decision.event_id == event.id
        for decision in decisions_before
    )
    temporary_title = "灰袍监察员折返"
    temporary_directive = (
        "让灰袍监察员再次经过东塔侧门，在门框上敲出一长两短的节奏后离开。"
    )

    mark_reply = await asyncio.wait_for(
        harness.agent.send(
            (
                "先不推进当前故事。"
                f"请把剧情沙盘里的“{original_title}”安排到下一次回到故事时发生。"
                f"这一次使用标题“{temporary_title}”，"
                f"并把具体剧情指令临时调整为“{temporary_directive}”。"
                "这些调整只对下一次安排生效，不要改动沙盘中的原事件。"
            ),
            mode="ooc",
        ),
        timeout=180,
    )

    call_names = main_tool_call_names(mark_reply)
    assert PLOT_SANDBOX_READ_TOOL_NAME in call_names
    assert PLOT_EVENT_MARK_NEXT_TOOL_NAME in call_names
    assert call_names.index(PLOT_SANDBOX_READ_TOOL_NAME) < call_names.index(
        PLOT_EVENT_MARK_NEXT_TOOL_NAME
    )
    assert any(
        _read_result_contains_event(invocation, event.id)
        for invocation in main_tool_invocations(
            mark_reply,
            PLOT_SANDBOX_READ_TOOL_NAME,
        )
    )
    matching_calls = [
        invocation
        for invocation in main_tool_invocations(
            mark_reply,
            PLOT_EVENT_MARK_NEXT_TOOL_NAME,
        )
        if invocation.arguments.get("event_id") == event.id
        and invocation.arguments.get("title") == temporary_title
        and invocation.arguments.get("directive") == temporary_directive
    ]
    assert matching_calls, "live LLM did not mark the requested Plot event"
    payload = matching_calls[-1].result
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert payload["pendingForNextWorldTurn"] is True
    assert payload["pendingInjection"]["sourceEventId"] == event.id
    assert payload["pendingInjection"]["eventTitle"] == temporary_title
    assert payload["pendingInjection"]["directive"] == temporary_directive

    pending = integration_data_gateway.plot_scheduling.get_pending_injection(
        harness.session_id
    )
    assert pending is not None
    assert pending.source_event_id == event.id
    assert pending.event_title == temporary_title
    assert pending.directive == temporary_directive
    source = integration_data_gateway.plot_scheduling.get_event(
        harness.story_id,
        event.id,
    )
    assert source is not None
    assert source.title == original_title
    assert source.directive == event.directive
    assert mark_reply.stats is not None
    assert mark_reply.stats.total_tokens > 0

    integration_data_gateway.rp_modules.upsert_session_override(
        harness.session_id,
        "narrative_outcome",
        enabled=False,
        config={},
    )
    status_before = status_snapshot(
        integration_data_gateway,
        harness.session_id,
    )
    world_call_offset = len(harness.calls)
    world_user_input = "我留在东塔侧门外，安静听着走廊里的动静。"

    world_reply = await asyncio.wait_for(
        harness.agent.send(world_user_input, mode="ic"),
        timeout=240,
    )

    assert world_reply.committed_turn_id is not None
    assert mark_reply.committed_turn_id is not None
    assert world_reply.committed_turn_id > mark_reply.committed_turn_id
    assert world_reply.text.strip()
    assert _PLOT_SUFFIX_OPEN not in world_reply.text
    assert _PLOT_SUFFIX_CLOSE not in world_reply.text

    world_calls = harness.calls[world_call_offset:]
    initial_main_call = next(
        call for call in world_calls if call.biz_key == AGENT_MAIN_BIZ_KEY
    )
    runtime_input = str(
        [
            message
            for message in initial_main_call.messages
            if message.get("role") == "user"
        ][-1].get("content", "")
    )
    assert world_user_input in runtime_input
    assert runtime_input.endswith(_PLOT_SUFFIX_CLOSE)
    assert runtime_input.index(world_user_input) < runtime_input.index(
        _PLOT_SUFFIX_OPEN
    )
    assert temporary_title in runtime_input
    assert temporary_directive in runtime_input
    assert all(
        temporary_directive not in str(message.get("content", ""))
        for message in initial_main_call.messages
        if message.get("role") == "system"
    )

    assert (
        integration_data_gateway.plot_scheduling.get_pending_injection(
            harness.session_id
        )
        is None
    )
    decision_ids_before = {decision.id for decision in decisions_before}
    new_decisions = [
        decision
        for decision in schedule_service.list_session_decisions(
            harness.session_id
        )
        if decision.id not in decision_ids_before
    ]
    manual_decisions = [
        decision
        for decision in new_decisions
        if decision.event_id == event.id
        and decision.selection_origin
        == models.PLOT_SELECTION_ORIGIN_MANUAL
    ]
    assert len(manual_decisions) == 1
    manual_decision = manual_decisions[0]
    assert manual_decision.turn_id == world_reply.committed_turn_id
    assert manual_decision.decision_status == models.PLOT_DECISION_TRIGGERED
    assert manual_decision.dispatch_mode == models.PLOT_DISPATCH_FORCED
    assert manual_decision.event_snapshot["eventTitle"] == temporary_title
    assert manual_decision.event_snapshot["directive"] == temporary_directive

    persisted_turn = [
        row
        for row in integration_data_gateway.messages.list(harness.session_id)
        if row.turn_id == world_reply.committed_turn_id
    ]
    assert [(row.role, row.mode) for row in persisted_turn] == [
        ("user", "ic"),
        ("assistant", "ic"),
    ]
    assert persisted_turn[0].content.endswith(world_user_input)
    assert temporary_directive not in persisted_turn[0].content
    assert _PLOT_SUFFIX_OPEN not in persisted_turn[0].content

    status_after = status_snapshot(
        integration_data_gateway,
        harness.session_id,
    )
    outcome = integration_data_gateway.narrative_outcomes.get_for_turn(
        harness.session_id,
        world_reply.committed_turn_id,
    )
    assert outcome is None
    verifier = await LLMClientManager.get().get_provider(
        AGENT_PLOT_SCHEDULER_BIZ_KEY
    )
    verification = await asyncio.wait_for(
        verify_plot_execution(
            verifier,
            user_input=world_user_input,
            plot_directives=(temporary_directive,),
            assistant_text=world_reply.text,
            outcome=None,
            status_before=status_before,
            status_after=status_after,
            player_character_name=DEMO_PLAYER_CHARACTER_NAME,
            message_mode="ic",
        ),
        timeout=120,
    )
    assert verification.plot_executed, verification
    assert verification.outcome_respected, verification
    assert verification.status_consistent, verification
    assert verification.player_agency_preserved, verification
