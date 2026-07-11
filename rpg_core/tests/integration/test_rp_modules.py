from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

import rpg_core.agent.agent as agent_module
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.context.rpg_context import LayerType
from rpg_core.context.fixed_layer.contributors import (
    RP_OUTPUT_TAG_NARRATION,
    TEXT_OUTPUT_FORMAT_NAME,
    TEXT_OUTPUT_FORMAT_SECTION_ID,
)
from rpg_core.rp_module_constants import (
    RP_MODULE_DICE_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID,
    RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID,
)
from rpg_core.tests.integration.conftest import _ensure_integration_session
from rpg_core.utils.watcher import get_watcher

pytestmark = pytest.mark.integration


class _NoLLMProvider:
    async def chat(self, messages, tools=None):  # noqa: ANN001
        raise AssertionError("RP module integration test must not call chat LLM")

    async def chat_stream(self, messages, tools=None):  # noqa: ANN001
        raise AssertionError("RP module integration test must not call streaming LLM")
        yield

    def get_default_model(self) -> str:
        return "no-llm-model"


class _NoLLMManager:
    def get_provider(
        self,
        _biz_key,
        overrides=None,
        *,
        provider_key=None,
    ):  # noqa: ANN001
        del overrides, provider_key
        return _NoLLMProvider()


@pytest.mark.asyncio
async def test_rp_modules_and_dice_commands_work_without_real_llm(
    monkeypatch,
    integration_settings,  # noqa: ARG001
    integration_workspace,
    integration_data_gateway,
):
    monkeypatch.setattr(agent_module.LLMManager, "get", classmethod(lambda cls: _NoLLMManager()))

    session_id = "integration_rp_modules"
    _ensure_integration_session(integration_data_gateway, integration_workspace, session_id)
    agent = RPGGameAgent(session_id=session_id)
    await agent._ensure_initialized()

    try:
        command_names = [command.name for command in agent.list_commands()]
        assert "/rp_modules" in command_names
        assert "/rp_module" in command_names
        assert "/roll" in command_names
        assert "/check_dc" in command_names
        assert "/check" not in command_names

        tool_names = [
            schema["function"]["name"]
            for schema in agent._tool_registry.get_openai_schemas()
        ]
        assert "rp_story_outcome" in tool_names
        assert "rp_dice_roll" not in tool_names
        assert "rp_dice_check_dc" not in tool_names

        ctx = agent._build_ctx_for_inspection("我想碰碰运气，看能不能在附近找到其他线索")
        fixed_content = ctx.render_layer(LayerType.FIXED) or ""
        assert f"[{RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID}]" in fixed_content
        assert f"[{TEXT_OUTPUT_FORMAT_SECTION_ID}]" in fixed_content
        assert "rp_story_outcome" in fixed_content
        assert "rp_dice_roll" not in fixed_content
        assert f"<{RP_OUTPUT_TAG_NARRATION}>" in fixed_content
        assert ctx.rp_modules.active is True
        runtime_content = ctx.render_layer(LayerType.RP_MODULES) or ""
        assert f"[{RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID}]" in runtime_content
        assert "rp_story_outcome(reason, actor?)" in runtime_content

        modules_result = await asyncio.wait_for(agent.execute_command("/rp_modules"), timeout=10)
        module_result = await asyncio.wait_for(agent.execute_command(f"/rp_module {RP_MODULE_DICE_NAME}"), timeout=10)
        outcome_module_result = await asyncio.wait_for(
            agent.execute_command(f"/rp_module {RP_MODULE_NARRATIVE_OUTCOME_NAME}"),
            timeout=10,
        )
        roll_result = await asyncio.wait_for(agent.execute_command("/roll 1d20"), timeout=10)
        check_result = await asyncio.wait_for(agent.execute_command("/check_dc 1d20 dc=12"), timeout=10)

        assert modules_result.handled is True
        assert RP_MODULE_DICE_NAME in modules_result.reply
        assert TEXT_OUTPUT_FORMAT_NAME not in modules_result.reply
        assert module_result.handled is True
        assert f"RP Module: {RP_MODULE_DICE_NAME}" in module_result.reply
        assert "/check_dc" in module_result.reply
        assert outcome_module_result.handled is True
        assert "rp_story_outcome" in outcome_module_result.reply
        assert roll_result.handled is True
        assert "骰子结果:" in roll_result.reply
        assert check_result.handled is True
        assert "检定结果:" in check_result.reply

        assert agent.history == []
        assert integration_data_gateway.messages.count(session_id) == 0
    finally:
        consumer = getattr(agent, "_consumer_task", None)
        if consumer is not None:
            consumer.cancel()
            with suppress(asyncio.CancelledError):
                await consumer

        watcher = get_watcher()
        watcher.stop()
        watcher.clear_all()
