from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from dataclasses import dataclass

import pytest
import pytest_asyncio

from commons.scene_time import SceneTime
from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_PLOT_SCHEDULER_BIZ_KEY,
)
from llm_client.manager import LLMClientManager
from llm_client.provider import RemoteLLMProvider
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.rp_modules.narrative_outcome.models import (
    NARRATIVE_OUTCOME_DEFINITION_BY_CODE,
)
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
from tests.support.plot_execution_verifier import (
    PLOT_EXECUTION_VERIFIER_TOOL_NAME,
    verify_plot_execution,
)

pytestmark = [pytest.mark.integration, pytest.mark.live_llm]

_PLOT_SUFFIX_OPEN = "[engine_plot_directive]"
_PLOT_SUFFIX_CLOSE = "[/engine_plot_directive]"


@dataclass(frozen=True)
class _RecordedLiveCall:
    biz_key: str
    messages: list[dict]
    tools: list[dict] | None


@dataclass(frozen=True)
class _LivePlotHarness:
    agent: RPGGameAgent
    catalog: IntegrationCatalog
    calls: list[_RecordedLiveCall]


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


def _status_snapshot(gateway, session_id: str) -> dict[str, dict[str, str]]:
    return {
        table.name: {
            row.key: str(row.value or "")
            for row in table.document.rows
        }
        for table in gateway.status.list_tables(session_id)
    }


def _initial_main_call(calls: list[_RecordedLiveCall]) -> _RecordedLiveCall:
    return next(call for call in calls if call.biz_key == AGENT_MAIN_BIZ_KEY)


def _main_tool_names(reply) -> set[str]:  # noqa: ANN001
    names: set[str] = set()
    for record in reply.tool_records or []:
        for tool_call in record.assistant_message.get("tool_calls", []) or []:
            function = tool_call.get("function", {})
            names.add(str(function.get("name", "")))
    return names


def _verifier_calls(calls: list[_RecordedLiveCall]) -> list[_RecordedLiveCall]:
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


class _FixedOutcomeRng:
    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def randint(self, lower: int, upper: int) -> int:
        assert (lower, upper) == (1, 100)
        self.calls += 1
        return self.value


@pytest.mark.asyncio
async def test_live_soft_plot_is_judged_injected_and_executed(
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
            "当前地点就是可从窗户进入的集成测试大厅，机械鸟无需其它角色到场，"
            "与玩家观察环境的行动完全兼容。"
        ),
    )
    integration_data_gateway.rp_modules.upsert_session_override(
        session_id,
        "narrative_outcome",
        enabled=False,
        config={},
    )
    before = _status_snapshot(integration_data_gateway, session_id)
    user_input = "我留在原地保持沉默，只观察大厅里的世界变化。"

    reply = await asyncio.wait_for(
        harness.agent.send(user_input),
        timeout=240,
    )

    after = _status_snapshot(integration_data_gateway, session_id)
    decisions = PlotScheduleManagementService(
        integration_data_gateway.plot_scheduling
    ).list_session_decisions(session_id)
    assert len(decisions) == 1
    assert decisions[0].event_id == event.id
    assert decisions[0].decision_status == models.PLOT_DECISION_TRIGGERED
    assert _PLOT_SUFFIX_OPEN not in reply.text
    assert f'<rp-character name="{harness.catalog.character.name}">' not in reply.text
    assert any(
        call.source == "plot_scheduler"
        for call in (reply.stats.calls if reply.stats is not None else [])
    )

    main_call = _initial_main_call(harness.calls)
    current_user = [
        message for message in main_call.messages if message.get("role") == "user"
    ][-1]
    current_content = str(current_user.get("content", ""))
    assert current_content.endswith(_PLOT_SUFFIX_CLOSE)
    assert current_content.index(user_input) < current_content.index(_PLOT_SUFFIX_OPEN)
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
    assert persisted_user.endswith(user_input)
    assert backup_user.endswith(user_input)
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
            user_input=user_input,
            plot_directives=(directive,),
            assistant_text=reply.text,
            outcome=None,
            status_before=before,
            status_after=after,
            player_character_name=harness.catalog.character.name,
        ),
        timeout=120,
    )
    assert verification.plot_executed, verification
    assert verification.outcome_respected, verification
    assert verification.status_consistent, verification
    assert verification.player_agency_preserved, verification
    assert 1 <= len(_verifier_calls(harness.calls)) <= 2


@pytest.mark.asyncio
async def test_live_plot_outcome_and_status_update_are_composed(
    live_plot_harness,
    integration_data_gateway,
):
    harness = live_plot_harness
    session_id = harness.catalog.session.id
    directive = (
        "本轮正文必须在当前大厅现场直接描写“北塔信使”本人从门口进入，"
        "入场时仍亲手抱着明确称为“蓝月匣”的银色匣子；不得改成场外传闻、纸条、"
        "转述或只更新状态。这一现场入场本身不等于安全交付。随后依据本轮 "
        "Narrative Outcome 决定他能否把匣子交到玩家手里，不得用 Plot 指令覆盖裁定；"
        "若是失败类结果，也必须先完成现场入场，再让交付在现场失败并提供下一步。"
        "输出正文前，把已确认的交付结果写入普通状态表的“线索”字段，"
        "字段值必须包含“蓝月匣”。"
        "不得替玩家角色发言、行动、决定或描写心理。"
    )
    event = _seed_plot_event(
        integration_data_gateway,
        harness.catalog,
        title="北塔信使送匣",
        directive=directive,
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
    )
    fixed_rng = _FixedOutcomeRng(71)
    harness.agent._lifecycle.rp_module_registry._rng_factory = lambda: fixed_rng
    before = _status_snapshot(integration_data_gateway, session_id)
    user_input = (
        "请随机裁定北塔信使能否把蓝月匣安全送到我面前。"
        "我保持沉默，只观察世界与 NPC 的反应。"
    )

    reply = await asyncio.wait_for(
        harness.agent.send(user_input),
        timeout=240,
    )

    after = _status_snapshot(integration_data_gateway, session_id)
    outcome = integration_data_gateway.narrative_outcomes.get_for_turn(
        session_id,
        1,
    )
    assert outcome is not None
    assert outcome.outcome_code == "setback"
    assert fixed_rng.calls == 1
    decisions = PlotScheduleManagementService(
        integration_data_gateway.plot_scheduling
    ).list_session_decisions(session_id)
    assert len(decisions) == 1
    assert decisions[0].event_id == event.id
    assert decisions[0].decision_status == models.PLOT_DECISION_TRIGGERED
    assert _PLOT_SUFFIX_OPEN not in reply.text
    assert "status_table_set_values" in _main_tool_names(reply)

    clue_before = before["集成线索"]["线索"]
    clue_after = after["集成线索"]["线索"]
    assert clue_after != clue_before
    assert "蓝月匣" in clue_after

    main_call = _initial_main_call(harness.calls)
    current_user = [
        message for message in main_call.messages if message.get("role") == "user"
    ][-1]
    current_content = str(current_user.get("content", ""))
    assert current_content.endswith(_PLOT_SUFFIX_CLOSE)
    assert directive in current_content
    system_content = "\n".join(
        str(message.get("content", ""))
        for message in main_call.messages
        if message.get("role") == "system"
    )
    assert '"outcomeCode":"setback"' in system_content
    assert directive not in system_content

    persisted = integration_data_gateway.messages.list(session_id)
    backup = integration_data_gateway.backup.messages.list(session_id)
    persisted_user = [row.content for row in persisted if row.role == "user"][-1]
    backup_user = [row.content for row in backup if row.role == "user"][-1]
    assert persisted_user.endswith(user_input)
    assert backup_user.endswith(user_input)
    assert _PLOT_SUFFIX_OPEN not in persisted_user
    assert _PLOT_SUFFIX_OPEN not in backup_user
    assert directive not in persisted_user
    assert directive not in backup_user

    definition = NARRATIVE_OUTCOME_DEFINITION_BY_CODE[outcome.outcome_code]
    public_outcome = {
        "outcomeCode": outcome.outcome_code,
        "reason": outcome.reason,
        "actor": outcome.actor,
        "narrativeGuidance": definition.narrative_guidance,
    }
    verifier = await LLMClientManager.get().get_provider(
        AGENT_PLOT_SCHEDULER_BIZ_KEY
    )
    verification = await asyncio.wait_for(
        verify_plot_execution(
            verifier,
            user_input=user_input,
            plot_directives=(directive,),
            assistant_text=reply.text,
            outcome=public_outcome,
            status_before=before,
            status_after=after,
            player_character_name=harness.catalog.character.name,
        ),
        timeout=120,
    )
    assert verification.plot_executed, verification
    assert verification.outcome_respected, verification
    assert verification.status_consistent, verification
    assert verification.player_agency_preserved, verification

    assert 1 <= len(_verifier_calls(harness.calls)) <= 2
