from __future__ import annotations

import asyncio

import pytest

from llm_client.keys import (
    AGENT_PLOT_SCHEDULER_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
)
from llm_client.manager import LLMClientManager
from rpg_core.rp_modules.constants import (
    RP_MODULE_NARRATIVE_OUTCOME_NAME,
    RP_MODULE_PLOT_SCHEDULER_NAME,
)
from rpg_core.rp_modules.narrative_outcome import (
    NARRATIVE_OUTCOME_TOOL_NAME,
)
from rpg_core.rp_modules.narrative_outcome.models import (
    NARRATIVE_OUTCOME_DEFINITION_BY_CODE,
)
from rpg_core.scene import (
    SCENE_ATTR_TOOL_NAME,
    SCENE_TIME_TOOL_NAME,
)
from rpg_core.status.tools import STATUS_TABLE_SET_VALUES_TOOL_NAME
from tests.support.live_agent import (
    first_call_with_tools,
    persisted_turn,
    status_record_arguments,
    status_record_result,
    status_snapshot,
    status_tool_records,
)
from tests.support.turn_execution_verifier import verify_turn_execution

pytestmark = [pytest.mark.integration, pytest.mark.live_llm]


def _disable_module(gateway, session_id: str, module_name: str) -> None:
    override = gateway.rp_modules.upsert_session_override(
        session_id,
        module_name,
        enabled=False,
        config={},
    )
    assert override is not None
    assert override.enabled is False


def _assert_committed_world_turn(
    gateway,
    *,
    session_id: str,
    turn_id: int,
    mode: str,
) -> None:
    rows = persisted_turn(gateway, session_id, turn_id)
    assert [(row.role, row.mode) for row in rows] == [
        ("user", mode),
        ("assistant", mode),
    ]
    assert all(not row.tool_call_id and not row.tool_calls_json for row in rows)


async def _verify_final_turn(
    harness,
    *,
    user_input: str,
    assistant_text: str,
    outcome: dict[str, object] | None,
    before: dict[str, dict[str, str]],
    after: dict[str, dict[str, str]],
    mode: str,
) -> None:
    verifier = await LLMClientManager.get().get_provider(
        AGENT_PLOT_SCHEDULER_BIZ_KEY
    )
    verification = await asyncio.wait_for(
        verify_turn_execution(
            verifier,
            user_input=user_input,
            assistant_text=assistant_text,
            outcome=outcome,
            status_before=before,
            status_after=after,
            player_character_name=harness.player_character_name,
            message_mode=mode,
        ),
        timeout=120,
    )
    assert verification.user_intent_addressed, verification
    assert verification.outcome_respected, verification
    assert verification.state_consistent, verification
    assert verification.player_agency_preserved, verification


@pytest.mark.asyncio
async def test_live_status_sub_agent_updates_scene_time_and_location(
    live_demo_harness,
    integration_data_gateway,
) -> None:
    harness = live_demo_harness
    _disable_module(
        integration_data_gateway,
        harness.session_id,
        RP_MODULE_PLOT_SCHEDULER_NAME,
    )
    _disable_module(
        integration_data_gateway,
        harness.session_id,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
    )
    before = status_snapshot(
        integration_data_gateway,
        harness.session_id,
    )
    call_offset = len(harness.calls)
    user_input = (
        "以 GM 指令推进这一小段：东塔侧门已经打开。"
        "Alice 与莫兰沿唯一通道走了二十分钟，"
        "在1 年 1 月 3 日 15 时 30 分抵达东塔地下库前厅。"
        "前厅里仍然只有 Alice 和莫兰。请从两人抵达后的现场继续描写。"
    )

    reply = await asyncio.wait_for(
        harness.agent.send(user_input, mode="gm"),
        timeout=240,
    )

    first_call_with_tools(
        harness.calls[call_offset:],
        biz_key=AGENT_STATUS_SUB_AGENT_BIZ_KEY,
        required_names={SCENE_TIME_TOOL_NAME, SCENE_ATTR_TOOL_NAME},
    )
    time_records = status_tool_records(reply, SCENE_TIME_TOOL_NAME)
    attr_records = status_tool_records(reply, SCENE_ATTR_TOOL_NAME)
    assert time_records, "live StatusSubAgent did not update Scene time"
    assert attr_records, "live StatusSubAgent did not update Scene attributes"
    assert any(
        record["success"] is True
        and record["changed"] is True
        and record["status"] == "changed"
        for record in time_records
    )
    time_args = status_record_arguments(time_records[-1])
    assert time_args.get("hour") == 15
    assert time_args.get("minute") == 30
    location_records = [
        record
        for record in attr_records
        if status_record_arguments(record).get("key") == "位置"
    ]
    assert location_records
    assert any(
        "地下库前厅"
        in str(status_record_arguments(record).get("value", ""))
        and record["success"] is True
        and record["changed"] is True
        for record in location_records
    )

    after = status_snapshot(
        integration_data_gateway,
        harness.session_id,
    )
    scene_after = after["奥术学院当前场景"]
    assert scene_after["时间"] == "1 年 1 月 3 日 15 时 30 分"
    assert "地下库前厅" in scene_after["位置"]
    assert reply.committed_turn_id is not None
    _assert_committed_world_turn(
        integration_data_gateway,
        session_id=harness.session_id,
        turn_id=reply.committed_turn_id,
        mode="gm",
    )
    await _verify_final_turn(
        harness,
        user_input=user_input,
        assistant_text=reply.text,
        outcome=None,
        before=before,
        after=after,
        mode="gm",
    )


@pytest.mark.asyncio
async def test_live_status_sub_agent_updates_existing_normal_status_values(
    live_demo_harness,
    integration_data_gateway,
) -> None:
    harness = live_demo_harness
    _disable_module(
        integration_data_gateway,
        harness.session_id,
        RP_MODULE_PLOT_SCHEDULER_NAME,
    )
    _disable_module(
        integration_data_gateway,
        harness.session_id,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
    )
    before = status_snapshot(
        integration_data_gateway,
        harness.session_id,
    )
    call_offset = len(harness.calls)
    user_input = (
        "我把刚采集的东塔侧门冷雾样本装进证物瓶，"
        "和登记簿、温度曲线一起交给莫兰完成封存。"
        "我明确把下一步调查目标改为进入地下库前厅，"
        "核对塞伦遗物与门内的温度记录，然后留在门外等莫兰收好证物。"
    )

    reply = await asyncio.wait_for(
        harness.agent.send(user_input, mode="ic"),
        timeout=240,
    )

    first_call_with_tools(
        harness.calls[call_offset:],
        biz_key=AGENT_STATUS_SUB_AGENT_BIZ_KEY,
        required_names={STATUS_TABLE_SET_VALUES_TOOL_NAME},
    )
    records = status_tool_records(
        reply,
        STATUS_TABLE_SET_VALUES_TOOL_NAME,
    )
    assert records, "live StatusSubAgent did not update normal status"
    changed_records = [
        record
        for record in records
        if record["success"] is True
        and record["changed"] is True
        and record["status"] == "changed"
    ]
    assert changed_records
    results = [status_record_result(record) for record in changed_records]
    assert all(isinstance(result, dict) for result in results)
    investigation_results = [
        result
        for result in results
        if isinstance(result, dict)
        and result.get("tableName") == "档案调查进度"
    ]
    assert investigation_results
    changed_keys = {
        str(change.get("key", ""))
        for result in investigation_results
        for change in result.get("changes", [])
    }
    assert "已封存证据" in changed_keys
    assert "下一目标" in changed_keys

    after = status_snapshot(
        integration_data_gateway,
        harness.session_id,
    )
    investigation_after = after["档案调查进度"]
    assert "冷雾" in investigation_after["已封存证据"]
    assert (
        "地下库前厅" in investigation_after["下一目标"]
        or "塞伦" in investigation_after["下一目标"]
    )
    assert reply.committed_turn_id is not None
    _assert_committed_world_turn(
        integration_data_gateway,
        session_id=harness.session_id,
        turn_id=reply.committed_turn_id,
        mode="ic",
    )
    await _verify_final_turn(
        harness,
        user_input=user_input,
        assistant_text=reply.text,
        outcome=None,
        before=before,
        after=after,
        mode="ic",
    )


@pytest.mark.asyncio
async def test_live_status_sub_agent_adjudicates_and_main_agent_executes_outcome(
    live_demo_harness,
    integration_data_gateway,
) -> None:
    harness = live_demo_harness
    _disable_module(
        integration_data_gateway,
        harness.session_id,
        RP_MODULE_PLOT_SCHEDULER_NAME,
    )
    before = status_snapshot(
        integration_data_gateway,
        harness.session_id,
    )
    call_offset = len(harness.calls)
    user_input = (
        "我把旧式火漆钥匙插入东塔侧门的锁孔，"
        "尝试在不触发学院警报的情况下打开地下库。"
        "这个结果交给随机裁定，我不预设成败，"
        "先停手等门锁和警报装置给出反应。"
    )

    reply = await asyncio.wait_for(
        harness.agent.send(user_input, mode="ic"),
        timeout=240,
    )

    first_call_with_tools(
        harness.calls[call_offset:],
        biz_key=AGENT_STATUS_SUB_AGENT_BIZ_KEY,
        required_names={NARRATIVE_OUTCOME_TOOL_NAME},
    )
    records = status_tool_records(reply, NARRATIVE_OUTCOME_TOOL_NAME)
    assert len(records) == 1
    record = records[0]
    assert record["success"] is True
    assert record["status"] == "outcome_staged"
    assert record["stage"] == "outcome"
    arguments = status_record_arguments(record)
    assert str(arguments.get("reason", "")).strip()
    result = status_record_result(record)
    assert isinstance(result, dict)
    assert result["outcomeCode"] in NARRATIVE_OUTCOME_DEFINITION_BY_CODE
    assert str(result["reason"]).strip()

    assert reply.committed_turn_id is not None
    stored = integration_data_gateway.narrative_outcomes.get_for_turn(
        harness.session_id,
        reply.committed_turn_id,
    )
    assert stored is not None
    assert stored.outcome_code == result["outcomeCode"]
    assert stored.reason == result["reason"]
    assert stored.actor == str(result.get("actor", ""))
    definition = NARRATIVE_OUTCOME_DEFINITION_BY_CODE[stored.outcome_code]
    public_outcome = {
        "outcomeCode": stored.outcome_code,
        "reason": stored.reason,
        "actor": stored.actor,
        "narrativeGuidance": definition.narrative_guidance,
    }
    after = status_snapshot(
        integration_data_gateway,
        harness.session_id,
    )
    _assert_committed_world_turn(
        integration_data_gateway,
        session_id=harness.session_id,
        turn_id=reply.committed_turn_id,
        mode="ic",
    )
    await _verify_final_turn(
        harness,
        user_input=user_input,
        assistant_text=reply.text,
        outcome=public_outcome,
        before=before,
        after=after,
        mode="ic",
    )
