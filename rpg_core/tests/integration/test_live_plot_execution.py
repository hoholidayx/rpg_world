from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import pytest
import pytest_asyncio

from commons.scene_time import SceneTime
from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_PLOT_SCHEDULER_BIZ_KEY,
)
from llm_client.manager import LLMClientManager
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.rp_modules.plot_scheduler import (
    CreatePlotEventCommand,
    CreatePlotPoolCommand,
    PlotScheduleManagementService,
)
from rpg_data import models
from tests.support.backend import (
    IntegrationCatalog,
    create_integration_session,
    shutdown_agent,
)
from tests.support.live_agent import RecordedLiveCall, status_snapshot
from tests.support.plot_execution_verifier import (
    PLOT_EXECUTION_VERIFIER_TOOL_NAME,
    verify_plot_execution,
)

pytestmark = [pytest.mark.integration, pytest.mark.live_llm]

_PLOT_SUFFIX_OPEN = "[engine_plot_directive]"
_PLOT_SUFFIX_CLOSE = "[/engine_plot_directive]"


@dataclass(frozen=True)
class _LivePlotHarness:
    agent: RPGGameAgent
    catalog: IntegrationCatalog
    calls: list[RecordedLiveCall]


@pytest_asyncio.fixture
async def live_plot_harness(
    request,
    integration_settings,  # noqa: ARG001
    integration_workspace,
    integration_data_gateway,
    live_call_recorder,
):
    try:
        await LLMClientManager.get().client.health()
    except Exception:
        pytest.skip("standalone LLM service is not available")
    safe_name = re.sub(r"[^A-Za-z0-9_]", "_", request.node.name)
    session_id = f"live_plot_{safe_name}"[:80]
    catalog = create_integration_session(
        integration_data_gateway,
        integration_workspace,
        session_id,
        with_status=True,
    )
    agent = RPGGameAgent(session_id=session_id)
    await agent.initialize()
    try:
        yield _LivePlotHarness(agent, catalog, live_call_recorder)
    finally:
        await shutdown_agent(agent)
        await LLMClientManager.areset()


def _seed_plot_event(
    gateway,
    catalog: IntegrationCatalog,
    *,
    title: str,
    directive: str,
    dispatch_mode: str,
    suitability_hint: str = "",
):
    service = PlotScheduleManagementService(gateway.plot_scheduling)
    pool = service.create_pool(
        CreatePlotPoolCommand(
            workspace_id=catalog.workspace_id,
            story_id=catalog.story.id,
            name=f"{title}测试池",
            selection_mode=models.PLOT_POOL_SEQUENTIAL,
            priority=100,
        )
    )
    return service.create_event(
        CreatePlotEventCommand(
            workspace_id=catalog.workspace_id,
            story_id=catalog.story.id,
            pool_id=pool.id,
            title=title,
            directive=directive,
            suitability_hint=suitability_hint,
            dispatch_mode=dispatch_mode,
            scheduled_time=SceneTime(2, 3, 4, 5),
        )
    )


def _initial_main_call(calls: list[RecordedLiveCall]) -> RecordedLiveCall:
    return next(call for call in calls if call.biz_key == AGENT_MAIN_BIZ_KEY)


def _verifier_calls(calls: list[RecordedLiveCall]) -> list[RecordedLiveCall]:
    return [
        call
        for call in calls
        if call.biz_key == AGENT_PLOT_SCHEDULER_BIZ_KEY
        and any(
            schema.get("function", {}).get("name")
            == PLOT_EXECUTION_VERIFIER_TOOL_NAME
            for schema in call.tools or []
        )
    ]


@pytest.mark.asyncio
async def test_live_scene_change_schedules_soft_plot_for_following_turn(
    live_plot_harness,
    integration_data_gateway,
):
    harness = live_plot_harness
    session_id = harness.catalog.session.id
    directive = (
        "让一只明确称为“蓝羽机械鸟”的机械鸟从窗外飞入当前大厅，"
        "当场落下一封带有“七号钟塔”蜡印的信。必须在本轮把事件作为世界事实"
        "自然开始，不得只讨论可能性；不得替玩家角色发言、行动或决定。"
    )
    event = _seed_plot_event(
        integration_data_gateway,
        harness.catalog,
        title="蓝羽机械鸟来信",
        directive=directive,
        dispatch_mode=models.PLOT_DISPATCH_SOFT,
        suitability_hint=(
            "当前地点是有高窗的钟楼前厅，机械鸟无需其它角色到场，"
            "与玩家观察环境的行动完全兼容。"
        ),
    )
    integration_data_gateway.rp_modules.upsert_session_override(
        session_id,
        "narrative_outcome",
        enabled=False,
        config={},
    )
    before_change = status_snapshot(integration_data_gateway, session_id)
    change_input = (
        "我离开集成测试大厅，沿北侧走廊走了十分钟，"
        "在 2 年 3 月 4 日 5 时 10 分走进钟楼前厅。"
        "前厅里只有我。我在高窗旁停下观察。"
    )
    first_call_offset = len(harness.calls)

    change_reply = await asyncio.wait_for(
        harness.agent.send(change_input, mode="ic"),
        timeout=240,
    )

    after_change = status_snapshot(integration_data_gateway, session_id)
    assert after_change["集成当前场景"] != before_change["集成当前场景"]
    assert change_reply.committed_turn_id is not None
    assert (
        integration_data_gateway.plot_scheduling.get_scene_opportunity(
            session_id
        )
        is not None
    )
    opportunity = (
        integration_data_gateway.plot_scheduling.get_scene_opportunity(
            session_id
        )
    )
    assert opportunity is not None
    assert opportunity.source_turn_id == change_reply.committed_turn_id
    schedule_service = PlotScheduleManagementService(
        integration_data_gateway.plot_scheduling
    )
    assert schedule_service.list_session_decisions(session_id) == []
    first_calls = harness.calls[first_call_offset:]
    assert not any(
        call.biz_key == AGENT_PLOT_SCHEDULER_BIZ_KEY
        for call in first_calls
    )
    first_main_call = _initial_main_call(first_calls)
    first_runtime_input = str(
        [
            message
            for message in first_main_call.messages
            if message.get("role") == "user"
        ][-1].get("content", "")
    )
    assert change_input in first_runtime_input
    assert _PLOT_SUFFIX_OPEN not in first_runtime_input
    first_persisted_user = [
        row.content
        for row in integration_data_gateway.messages.list(session_id)
        if row.turn_id == change_reply.committed_turn_id
        and row.role == models.MESSAGE_ROLE_USER
    ][0]
    assert first_persisted_user.endswith(change_input)
    assert _PLOT_SUFFIX_OPEN not in first_persisted_user

    status_before_execution = after_change
    execution_input = (
        "我站在钟楼前厅的高窗旁，没有出声，只留意接下来发生的变化。"
    )
    second_call_offset = len(harness.calls)
    reply = await asyncio.wait_for(
        harness.agent.send(execution_input),
        timeout=240,
    )

    status_after_execution = status_snapshot(
        integration_data_gateway,
        session_id,
    )
    decisions = schedule_service.list_session_decisions(session_id)
    assert len(decisions) == 1
    assert decisions[0].event_id == event.id
    assert decisions[0].turn_id == reply.committed_turn_id
    assert decisions[0].decision_status == models.PLOT_DECISION_TRIGGERED
    assert _PLOT_SUFFIX_OPEN not in reply.text
    assert f'<rp-character name="{harness.catalog.character.name}">' not in reply.text
    assert any(
        call.source == "plot_scheduler"
        for call in (reply.stats.calls if reply.stats is not None else [])
    )

    second_calls = harness.calls[second_call_offset:]
    main_call = _initial_main_call(second_calls)
    current_user = [
        message for message in main_call.messages if message.get("role") == "user"
    ][-1]
    current_content = str(current_user.get("content", ""))
    assert current_content.endswith(_PLOT_SUFFIX_CLOSE)
    assert current_content.index(execution_input) < current_content.index(
        _PLOT_SUFFIX_OPEN
    )
    assert directive in current_content
    assert all(
        directive not in str(message.get("content", ""))
        for message in main_call.messages
        if message.get("role") == "system"
    )

    persisted = integration_data_gateway.messages.list(session_id)
    backup = integration_data_gateway.backup.messages.list(session_id)
    persisted_user = [row.content for row in persisted if row.role == "user"][-1]
    backup_user = [row.content for row in backup if row.role == "user"][-1]
    assert persisted_user.endswith(execution_input)
    assert backup_user.endswith(execution_input)
    assert _PLOT_SUFFIX_OPEN not in persisted_user
    assert _PLOT_SUFFIX_OPEN not in backup_user
    assert directive not in persisted_user
    assert directive not in backup_user

    verifier = await LLMClientManager.get().get_provider(
        AGENT_PLOT_SCHEDULER_BIZ_KEY
    )
    verification = await asyncio.wait_for(
        verify_plot_execution(
            verifier,
            user_input=execution_input,
            plot_directives=(directive,),
            assistant_text=reply.text,
            outcome=None,
            status_before=status_before_execution,
            status_after=status_after_execution,
            player_character_name=harness.catalog.character.name,
        ),
        timeout=120,
    )
    assert verification.plot_executed, verification
    assert verification.outcome_respected, verification
    assert verification.status_consistent, verification
    assert verification.player_agency_preserved, verification
    assert 1 <= len(_verifier_calls(harness.calls)) <= 2

    next_opportunity = (
        integration_data_gateway.plot_scheduling.get_scene_opportunity(
            session_id
        )
    )
    if (
        status_after_execution["集成当前场景"]
        == status_before_execution["集成当前场景"]
    ):
        assert next_opportunity is None
    else:
        assert next_opportunity is not None
        assert next_opportunity.source_turn_id == reply.committed_turn_id
