from __future__ import annotations

import random

import pytest

from rpg_core.agent.tools import BaseTool
from rpg_core.rp_modules import registry as registry_module
from rpg_core.rp_modules.constants import (
    RP_MODULE_DICE_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID,
    RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID,
)
from rpg_core.rp_modules.models import ModuleContextRequest
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.settings import (
    DiceModuleSettings,
    NarrativeOutcomeModuleSettings,
    RPModuleSettings,
)


def test_registry_loads_default_modules():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(),
        rng_factory=lambda: random.Random(0),
    )

    assert [module.name for module in registry.enabled_modules()] == [
        RP_MODULE_DICE_NAME,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
    ]
    assert [section.id for section in registry.get_fixed_sections()] == [
        RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID
    ]
    assert [tool.name for tool in registry.get_tools()] == ["rp_story_outcome"]
    assert registry.get_runtime_sections() == []
    assert [command.name for command in registry.get_commands()] == [
        "/rp_modules",
        "/rp_module",
        "/roll",
        "/check_dc",
    ]


def test_registry_global_disable_returns_empty_collections():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(enabled=False),
    )

    assert registry.enabled_modules() == []
    assert registry.get_fixed_sections() == []
    assert registry.get_tools() == []
    assert registry.get_commands() == []
    assert registry.get_runtime_sections() == []


def test_registry_keeps_narrative_module_and_framework_commands_when_dice_disabled():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(dice=DiceModuleSettings(enabled=False)),
    )

    assert [module.name for module in registry.enabled_modules()] == [
        RP_MODULE_NARRATIVE_OUTCOME_NAME
    ]
    assert [section.id for section in registry.get_fixed_sections()] == [
        RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID
    ]
    assert [command.name for command in registry.get_commands()] == [
        "/rp_modules",
        "/rp_module",
    ]
    status = registry.module_status(RP_MODULE_DICE_NAME)
    assert status.enabled is False
    assert status.config_summary["default_dc"] == 12


def test_narrative_fixed_contract_uses_semantic_scene_gate():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(
            narrative_outcome=NarrativeOutcomeModuleSettings(
                auto_adjudication_enabled=True
            )
        ),
    )

    content = registry.get_fixed_sections()[0].content

    assert "每轮叙事前" in content
    assert "用户完整语义、当前场景和状态" in content
    assert "未知信息、角色能力" in content
    assert "NPC/世界反应" in content
    assert "必须先调用 rp_story_outcome" in content
    assert "表达式、DC、修正值" in content
    assert "不得只建议" in content
    assert "reason 必须完整描述本次裁定的整体目标边界" in content
    assert "reason 是不可缩小的整体目标" in content
    assert "当前 scene 与普通状态表" not in content


def test_narrative_fixed_contract_disables_only_implicit_auto_adjudication():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(
            narrative_outcome=NarrativeOutcomeModuleSettings(
                auto_adjudication_enabled=False
            )
        ),
    )

    content = registry.get_fixed_sections()[0].content

    assert "自动剧情裁定已关闭" in content
    assert "用户明确要求" in content
    assert "每轮叙事前" not in content


def test_status_preflight_respects_auto_adjudication_setting():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(
            narrative_outcome=NarrativeOutcomeModuleSettings(
                auto_adjudication_enabled=False
            )
        ),
    )

    assert registry.get_status_preflight_tools("我向 Alice 点头问好") == []
    assert [
        tool.name
        for tool in registry.get_status_preflight_tools("请为潜行做一次检定")
    ] == ["rp_story_outcome"]


@pytest.mark.parametrize(
    "user_input",
    [
        "我想碰碰运气，看能不能在附近找到其他线索",
        "请为这次潜行做一次检定",
        "Roll 1d20 for the guard check",
        "这次交给运气随机裁定",
    ],
)
def test_narrative_explicit_random_intent_adds_turn_directive(user_input: str):
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(),
    )

    sections = registry.get_runtime_sections(
        ModuleContextRequest(session_id="s1", user_input=user_input)
    )

    assert [section.id for section in sections] == [
        RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
    ]
    assert "本轮已明确把外部结果交给随机裁定" in sections[0].content
    assert "rp_story_outcome(reason, actor?)" in sections[0].content
    assert "不要询问表达式、DC" in sections[0].content


def test_narrative_ordinary_roleplay_does_not_add_turn_directive():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(),
    )

    sections = registry.get_runtime_sections(
        ModuleContextRequest(session_id="s1", user_input="我向 Alice 点头问好。")
    )

    assert sections == []


@pytest.mark.parametrize(
    "user_input",
    [
        "这轮不要掷骰，直接继续叙事。",
        "Do not roll dice for this scene.",
        "Check the clock on the wall.",
    ],
)
def test_narrative_negated_or_plain_check_text_does_not_force_turn_directive(user_input: str):
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(),
    )

    sections = registry.get_runtime_sections(
        ModuleContextRequest(session_id="s1", user_input=user_input)
    )

    assert sections == []


def test_registry_rejects_duplicate_public_tool_names(monkeypatch):
    class DuplicateTool(BaseTool):
        name = "rp_duplicate"
        description = "duplicate"

        def parameters(self):
            return {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            return "ok"

    class DuplicateDiceModule:
        name = RP_MODULE_DICE_NAME

        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_tools(self):
            return [DuplicateTool(), DuplicateTool()]

        def get_fixed_sections(self):
            return []

        def get_runtime_sections(self, request):
            return []

        def get_commands(self):
            return []

    monkeypatch.setattr(registry_module, "DiceModule", DuplicateDiceModule)

    with pytest.raises(ValueError, match="Duplicate RP module tool name"):
        RPModuleRegistry(
            session_id="s1",
            world_name="world",
            settings=RPModuleSettings(),
        )
