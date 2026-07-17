from __future__ import annotations

import random

import pytest

from rpg_core.tooling.base import BaseTool
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
from rpg_data.services import get_data_service_gateway


def _runtime(tmp_path, settings: RPModuleSettings | None = None):
    gateway = get_data_service_gateway(tmp_path / "registry.sqlite3")
    registry = RPModuleRegistry(
        settings=settings or RPModuleSettings(),
        rng_factory=lambda: random.Random(0),
        gateway_provider=lambda: gateway,
    )
    snapshot = registry.resolve_snapshot("s_forest001")
    return registry, snapshot, registry.create_runtime(snapshot)


def test_registry_loads_default_modules(tmp_path):
    registry, _snapshot, runtime = _runtime(tmp_path)

    assert [module.name for module in runtime.enabled_modules()] == [
        RP_MODULE_DICE_NAME,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
    ]
    assert [section.id for section in runtime.get_fixed_sections()] == [
        RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID
    ]
    assert [tool.name for tool in runtime.get_tools()] == ["rp_story_outcome"]
    assert runtime.get_runtime_sections(ModuleContextRequest(session_id="s_forest001")) == []
    assert [command.name for command in registry.get_commands("s_forest001")] == [
        "/rp_modules",
        "/rp_module",
        "/roll",
        "/check_dc",
    ]


def test_registry_global_disable_returns_empty_collections(tmp_path):
    registry, _snapshot, runtime = _runtime(
        tmp_path,
        RPModuleSettings(enabled=False),
    )

    assert runtime.enabled_modules() == []
    assert runtime.get_fixed_sections() == []
    assert runtime.get_tools() == []
    assert [command.name for command in registry.get_commands("s_forest001")] == [
        "/rp_modules",
        "/rp_module",
    ]
    assert runtime.get_runtime_sections(ModuleContextRequest(session_id="s_forest001")) == []


def test_registry_keeps_narrative_module_and_framework_commands_when_dice_disabled(tmp_path):
    registry, snapshot, runtime = _runtime(
        tmp_path,
        RPModuleSettings(dice=DiceModuleSettings(enabled=False)),
    )

    assert [module.name for module in runtime.enabled_modules()] == [
        RP_MODULE_NARRATIVE_OUTCOME_NAME
    ]
    assert [section.id for section in runtime.get_fixed_sections()] == [
        RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID
    ]
    assert [command.name for command in registry.get_commands("s_forest001")] == [
        "/rp_modules",
        "/rp_module",
    ]
    selected = snapshot.get(RP_MODULE_DICE_NAME)
    assert selected is not None
    assert selected.effective_enabled is False
    assert selected.effective_config["default_dc"] == 12


def test_narrative_fixed_contract_uses_semantic_scene_gate(tmp_path):
    _registry, _snapshot, runtime = _runtime(
        tmp_path,
        RPModuleSettings(
            narrative_outcome=NarrativeOutcomeModuleSettings(
                auto_adjudication_enabled=True
            )
        ),
    )

    content = runtime.get_fixed_sections()[0].content

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


def test_narrative_fixed_contract_disables_only_implicit_auto_adjudication(tmp_path):
    _registry, _snapshot, runtime = _runtime(
        tmp_path,
        RPModuleSettings(
            narrative_outcome=NarrativeOutcomeModuleSettings(
                auto_adjudication_enabled=False
            )
        ),
    )

    content = runtime.get_fixed_sections()[0].content

    assert "自动剧情裁定已关闭" in content
    assert "用户明确要求" in content
    assert "每轮叙事前" not in content


def test_status_preflight_respects_auto_adjudication_setting(tmp_path):
    _registry, _snapshot, runtime = _runtime(
        tmp_path,
        RPModuleSettings(
            narrative_outcome=NarrativeOutcomeModuleSettings(
                auto_adjudication_enabled=False
            )
        ),
    )

    assert runtime.get_status_preflight_tools("我向 Alice 点头问好") == []
    assert [
        tool.name
        for tool in runtime.get_status_preflight_tools("请为潜行做一次检定")
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
def test_narrative_explicit_random_intent_adds_turn_directive(user_input: str, tmp_path):
    _registry, _snapshot, runtime = _runtime(tmp_path)

    sections = runtime.get_runtime_sections(
        ModuleContextRequest(session_id="s_forest001", user_input=user_input)
    )

    assert [section.id for section in sections] == [
        RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
    ]
    assert "本轮已明确把外部结果交给随机裁定" in sections[0].content
    assert "rp_story_outcome(reason, actor?)" in sections[0].content
    assert "不要询问表达式、DC" in sections[0].content


def test_narrative_ordinary_roleplay_does_not_add_turn_directive(tmp_path):
    _registry, _snapshot, runtime = _runtime(tmp_path)

    sections = runtime.get_runtime_sections(
        ModuleContextRequest(session_id="s_forest001", user_input="我向 Alice 点头问好。")
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
def test_narrative_negated_or_plain_check_text_does_not_force_turn_directive(user_input: str, tmp_path):
    _registry, _snapshot, runtime = _runtime(tmp_path)

    sections = runtime.get_runtime_sections(
        ModuleContextRequest(session_id="s_forest001", user_input=user_input)
    )

    assert sections == []


def test_registry_rejects_duplicate_public_tool_names(monkeypatch, tmp_path):
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
    gateway = get_data_service_gateway(tmp_path / "duplicate-tools.sqlite3")
    registry = RPModuleRegistry(gateway_provider=lambda: gateway)
    snapshot = registry.resolve_snapshot("s_forest001")

    with pytest.raises(ValueError, match="Duplicate RP module tool name"):
        registry.create_runtime(snapshot)


def test_snapshot_merges_story_and_session_config_with_story_capability_ceiling(tmp_path):
    gateway = get_data_service_gateway(tmp_path / "rp-module-selection.sqlite3")
    registry = RPModuleRegistry(gateway_provider=lambda: gateway)
    weights = {
        "critical_success": 10,
        "success": 30,
        "success_with_cost": 30,
        "setback": 25,
        "critical_failure": 5,
    }
    gateway.rp_modules.set_story_module(
        "demo_workspace",
        1,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        enabled=True,
        config={"auto_adjudication_enabled": False, "weights": weights},
    )
    gateway.rp_modules.set_session_override(
        "s_forest001",
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        enabled=True,
        config={"auto_adjudication_enabled": True},
    )

    first = registry.resolve_snapshot("s_forest001")
    selected = first.get(RP_MODULE_NARRATIVE_OUTCOME_NAME)
    assert selected is not None
    assert selected.effective_enabled is True
    assert selected.effective_config["auto_adjudication_enabled"] is True
    assert selected.effective_config["weights"] == weights
    assert selected.config_sources == {
        "auto_adjudication_enabled": "session",
        "weights": "story",
    }
    with pytest.raises(TypeError):
        selected.effective_config["weights"]["success"] = 1

    gateway.rp_modules.set_story_module(
        "demo_workspace",
        1,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        enabled=False,
        config={"auto_adjudication_enabled": False, "weights": weights},
    )
    second = registry.resolve_snapshot("s_forest001")
    assert second.get(RP_MODULE_NARRATIVE_OUTCOME_NAME).effective_enabled is False
    assert first.get(RP_MODULE_NARRATIVE_OUTCOME_NAME).effective_enabled is True
    disabled_runtime = registry.create_runtime(second)
    assert "rp_story_outcome" not in [tool.name for tool in disabled_runtime.get_tools()]
    assert all(
        section.id != RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID
        for section in disabled_runtime.get_fixed_sections()
    )


def test_dice_commands_follow_latest_story_mount_state(tmp_path):
    gateway = get_data_service_gateway(tmp_path / "rp-module-commands.sqlite3")
    registry = RPModuleRegistry(gateway_provider=lambda: gateway)
    assert "/roll" in [item.name for item in registry.get_commands("s_forest001")]

    gateway.rp_modules.set_story_module(
        "demo_workspace",
        1,
        RP_MODULE_DICE_NAME,
        enabled=False,
        config={},
    )
    names = [item.name for item in registry.get_commands("s_forest001")]
    assert names == ["/rp_modules", "/rp_module"]
