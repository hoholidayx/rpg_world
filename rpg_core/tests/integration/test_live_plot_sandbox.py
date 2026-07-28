from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass

import pytest
import pytest_asyncio

from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_PLOT_SCHEDULER_BIZ_KEY,
)
from llm_client.manager import LLMClientManager
from llm_client.provider import RemoteLLMProvider
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.rp_modules.plot_scheduler import PlotScheduleManagementService
from rpg_core.rp_modules.plot_scheduler.tools import (
    PLOT_EVENT_MARK_NEXT_TOOL_NAME,
    PLOT_SANDBOX_READ_TOOL_NAME,
)
from rpg_data import models
from tests.support.backend import shutdown_agent
from tests.support.plot_execution_verifier import verify_plot_execution

pytestmark = [pytest.mark.integration, pytest.mark.live_llm]

_DEMO_WORKSPACE_ID = "demo_workspace"
_DEMO_STORY_TITLE = "奥术学院 Demo"
_DEMO_SESSION_ID = "s_academy01"
_DEMO_PLAYER_CHARACTER_NAME = "Alice"
_PLOT_SUFFIX_OPEN = "[engine_plot_directive]"
_PLOT_SUFFIX_CLOSE = "[/engine_plot_directive]"


@dataclass(frozen=True)
class _RecordedLiveCall:
    biz_key: str
    messages: list[dict]
    tools: list[dict] | None


@dataclass(frozen=True)
class _LivePlotSandboxHarness:
    agent: RPGGameAgent
    workspace_id: str
    story_id: int
    session_id: str
    calls: list[_RecordedLiveCall]


@dataclass(frozen=True)
class _ToolInvocation:
    arguments: dict[str, object]
    result: dict[str, object]


@pytest.fixture
def live_call_recorder(monkeypatch) -> list[_RecordedLiveCall]:
    calls: list[_RecordedLiveCall] = []
    original_chat = RemoteLLMProvider.chat

    async def recorded_chat(self, messages, tools=None):  # noqa: ANN001, ANN202
        calls.append(
            _RecordedLiveCall(
                biz_key=self.biz_key,
                messages=deepcopy(messages),
                tools=deepcopy(tools),
            )
        )
        return await original_chat(self, messages, tools)

    monkeypatch.setattr(RemoteLLMProvider, "chat", recorded_chat)
    return calls


@pytest_asyncio.fixture
async def live_plot_sandbox_harness(
    integration_settings,  # noqa: ARG001
    integration_data_gateway,
    live_call_recorder,
):
    try:
        await LLMClientManager.get().client.health()
    except Exception:
        pytest.skip("standalone LLM service is not available")
    session = integration_data_gateway.sessions.get_session(_DEMO_SESSION_ID)
    assert session is not None
    assert session.workspace_id == _DEMO_WORKSPACE_ID
    story = integration_data_gateway.sessions.get_story(
        session.workspace_id,
        session.story_id,
    )
    assert story is not None
    assert story.title == _DEMO_STORY_TITLE
    agent = RPGGameAgent(session_id=session.id)
    await agent.initialize()
    try:
        yield _LivePlotSandboxHarness(
            agent,
            session.workspace_id,
            session.story_id,
            session.id,
            live_call_recorder,
        )
    finally:
        await shutdown_agent(agent)
        await LLMClientManager.areset()


def _demo_plot_event(
    gateway,
    harness: _LivePlotSandboxHarness,
    title: str,
):
    service = PlotScheduleManagementService(gateway.plot_scheduling)
    schedule = service.get_story_schedule(
        harness.workspace_id,
        harness.story_id,
    )
    assert schedule is not None
    return next(event for event in schedule.events if event.title == title)


def _status_snapshot(gateway, session_id: str) -> dict[str, dict[str, str]]:
    return {
        table.name: {
            row.key: str(row.value or "")
            for row in table.document.rows
        }
        for table in gateway.status.list_tables(session_id)
    }


def _tool_invocations(reply, tool_name: str) -> list[_ToolInvocation]:  # noqa: ANN001
    invocations: list[_ToolInvocation] = []
    for record in reply.tool_records or []:
        results_by_call_id = {
            str(result.get("tool_call_id", "")): result
            for result in record.tool_results
        }
        for tool_call in record.assistant_message.get("tool_calls", []) or []:
            function = tool_call.get("function", {})
            if function.get("name") != tool_name:
                continue
            call_id = str(tool_call.get("id", ""))
            tool_result = results_by_call_id.get(call_id)
            assert tool_result is not None, f"missing result for tool call {call_id!r}"
            arguments = json.loads(str(function.get("arguments", "{}")))
            result = json.loads(str(tool_result.get("content", "{}")))
            assert isinstance(arguments, dict)
            assert isinstance(result, dict)
            invocations.append(_ToolInvocation(arguments, result))
    return invocations


def _tool_call_names(reply) -> list[str]:  # noqa: ANN001
    return [
        str(tool_call.get("function", {}).get("name", ""))
        for record in reply.tool_records or []
        for tool_call in record.assistant_message.get("tool_calls", []) or []
    ]


def _read_result_contains_event(
    invocation: _ToolInvocation,
    event_id: int,
) -> bool:
    payload = invocation.result
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
    live_plot_sandbox_harness,
    integration_data_gateway,
) -> None:
    harness = live_plot_sandbox_harness
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
        for invocation in _tool_invocations(reply, PLOT_SANDBOX_READ_TOOL_NAME)
        if invocation.arguments.get("resource") == "event"
        and invocation.arguments.get("id") == event.id
    ]
    assert matching_calls, "live LLM did not read the requested Plot event"
    payload = matching_calls[-1].result
    assert payload["ok"] is True
    assert payload["resource"] == "event"
    assert payload["view"] == "detail"
    assert payload["item"]["id"] == event.id
    assert payload["item"]["title"] == title
    assert payload["item"]["directive"] == event.directive
    assert not _tool_invocations(reply, PLOT_EVENT_MARK_NEXT_TOOL_NAME)
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
    live_plot_sandbox_harness,
    integration_data_gateway,
) -> None:
    harness = live_plot_sandbox_harness
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

    call_names = _tool_call_names(mark_reply)
    assert PLOT_SANDBOX_READ_TOOL_NAME in call_names
    assert PLOT_EVENT_MARK_NEXT_TOOL_NAME in call_names
    assert call_names.index(PLOT_SANDBOX_READ_TOOL_NAME) < call_names.index(
        PLOT_EVENT_MARK_NEXT_TOOL_NAME
    )
    assert any(
        _read_result_contains_event(invocation, event.id)
        for invocation in _tool_invocations(
            mark_reply,
            PLOT_SANDBOX_READ_TOOL_NAME,
        )
    )
    matching_calls = [
        invocation
        for invocation in _tool_invocations(
            mark_reply,
            PLOT_EVENT_MARK_NEXT_TOOL_NAME,
        )
        if invocation.arguments.get("event_id") == event.id
        and invocation.arguments.get("title") == temporary_title
        and invocation.arguments.get("directive") == temporary_directive
    ]
    assert matching_calls, "live LLM did not mark the requested Plot event"
    payload = matching_calls[-1].result
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
    status_before = _status_snapshot(
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

    status_after = _status_snapshot(
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
            player_character_name=_DEMO_PLAYER_CHARACTER_NAME,
            message_mode="ic",
        ),
        timeout=120,
    )
    assert verification.plot_executed, verification
    assert verification.outcome_respected, verification
    assert verification.status_consistent, verification
    assert verification.player_agency_preserved, verification
