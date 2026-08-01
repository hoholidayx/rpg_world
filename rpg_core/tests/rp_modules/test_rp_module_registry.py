from __future__ import annotations

import random

import pytest

import rpg_core.rp_modules.registry as registry_module
from rpg_core.rp_modules.application import RPModuleApplicationService
from rpg_core.rp_modules.constants import (
    RP_MODULE_DICE_NAME,
    RP_MODULE_MESSAGE_MODE_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID,
    RP_MODULE_PLOT_SCHEDULER_NAME,
    RP_MODULE_PLOT_SCHEDULER_SECTION_ID,
)
from rpg_core.rp_modules.models import ModuleContextRequest
from rpg_core.tooling.base import BaseTool
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
    )
    service = RPModuleApplicationService(registry, gateway.rp_modules)
    snapshot = service.resolve_snapshot("s_forest001")
    return service, snapshot, service.create_runtime(snapshot)


def test_registry_loads_default_modules(tmp_path):
    registry, _snapshot, runtime = _runtime(tmp_path)

    assert [module.name for module in runtime.enabled_modules()] == [
        RP_MODULE_DICE_NAME,
        RP_MODULE_MESSAGE_MODE_NAME,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        RP_MODULE_PLOT_SCHEDULER_NAME,
    ]
    assert [section.id for section in runtime.get_fixed_sections()] == [
        RP_MODULE_PLOT_SCHEDULER_SECTION_ID,
    ]
    assert [tool.name for tool in runtime.get_tools()] == ["rp_story_outcome"]
    assert [
        section.id
        for section in runtime.get_runtime_sections(
            ModuleContextRequest(session_id="s_forest001")
        )
    ] == [RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID]
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
        RP_MODULE_MESSAGE_MODE_NAME,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        RP_MODULE_PLOT_SCHEDULER_NAME,
    ]
    assert [section.id for section in runtime.get_fixed_sections()] == [
        RP_MODULE_PLOT_SCHEDULER_SECTION_ID,
    ]
    assert [command.name for command in registry.get_commands("s_forest001")] == [
        "/rp_modules",
        "/rp_module",
    ]
    selected = snapshot.get(RP_MODULE_DICE_NAME)
    assert selected is not None
    assert selected.effective_enabled is False
    assert selected.effective_config["default_dc"] == 12


def test_narrative_dynamic_contract_uses_semantic_scene_gate(tmp_path):
    _registry, _snapshot, runtime = _runtime(
        tmp_path,
        RPModuleSettings(
            narrative_outcome=NarrativeOutcomeModuleSettings(
                auto_adjudication_enabled=True
            )
        ),
    )

    content = next(
        section.content
        for section in runtime.get_runtime_sections(
            ModuleContextRequest(session_id="s_forest001", user_input="我尝试说服守卫")
        )
        if section.id == RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
    )
    assert runtime.get_fixed_sections() == [
        section
        for section in runtime.get_fixed_sections()
        if section.id == RP_MODULE_PLOT_SCHEDULER_SECTION_ID
    ]

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


def test_narrative_dynamic_contract_disables_only_implicit_auto_adjudication(tmp_path):
    _registry, _snapshot, runtime = _runtime(
        tmp_path,
        RPModuleSettings(
            narrative_outcome=NarrativeOutcomeModuleSettings(
                auto_adjudication_enabled=False
            )
        ),
    )

    ordinary_sections = runtime.get_runtime_sections(
        ModuleContextRequest(session_id="s_forest001", user_input="我向守卫点头")
    )
    explicit_sections = runtime.get_runtime_sections(
        ModuleContextRequest(
            session_id="s_forest001",
            user_input="请为这次潜行做一次检定",
        )
    )

    assert all(
        section.id != RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
        for section in ordinary_sections
    )
    content = next(
        section.content
        for section in explicit_sections
        if section.id == RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
    )
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
    ("user_input", "message_mode", "expected"),
    [
        ("以GM已确认事实固定推进三十分钟。", "gm", False),
        ("推进场景。", "gm", False),
        ("让主管查看申请并按现场情况回应。", "gm", False),
        ("更正刚才已确认的事项名称。", "neutral", False),
        ("以GM指令随机决定工作人员是否注意到异常。", "gm", True),
        ("结果保持未知，由颜沁自己决定是否回应。", "gm", True),
        ("以GM已确认事实推进，但随机决定门外是否有人。", "gm", True),
        ("请掷骰决定结果。", "ooc", False),
    ],
)
def test_narrative_eligibility_keeps_prompt_and_tools_in_lockstep(
    user_input: str,
    message_mode: str,
    expected: bool,
    tmp_path,
) -> None:
    _registry, _snapshot, runtime = _runtime(tmp_path)
    request = ModuleContextRequest(
        session_id="s_forest001",
        user_input=user_input,
        message_mode=message_mode,
    )

    has_section = any(
        section.id == RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
        for section in runtime.get_runtime_sections(request)
    )
    status_tools = runtime.get_status_preflight_tools(user_input, message_mode)
    main_tools = runtime.get_main_agent_tools(user_input, message_mode)

    assert has_section is expected
    assert ("rp_story_outcome" in {tool.name for tool in status_tools}) is expected
    assert ("rp_story_outcome" in {tool.name for tool in main_tools}) is expected


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
    assert "本轮已检测到用户明确把外部结果交给随机裁定" in sections[0].content
    assert "rp_story_outcome(reason, actor?)" in sections[0].content
    assert "表达式、DC、修正值" in sections[0].content


def test_narrative_ordinary_roleplay_gets_dynamic_contract_without_force_marker(tmp_path):
    _registry, _snapshot, runtime = _runtime(tmp_path)

    sections = runtime.get_runtime_sections(
        ModuleContextRequest(session_id="s_forest001", user_input="我向 Alice 点头问好。")
    )

    assert [section.id for section in sections] == [
        RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
    ]
    assert "每轮叙事前" in sections[0].content
    assert "本轮已检测到用户明确" not in sections[0].content


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

    assert [section.id for section in sections] == [
        RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
    ]
    assert "本轮已检测到用户明确" not in sections[0].content


def test_narrative_contract_is_absent_from_ooc_runtime(tmp_path):
    _registry, _snapshot, runtime = _runtime(tmp_path)

    sections = runtime.get_runtime_sections(ModuleContextRequest(
        session_id="s_forest001",
        user_input="讨论一下裁定规则",
        message_mode="ooc",
    ))

    assert all(
        section.id != RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
        for section in sections
    )


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
    registry = RPModuleRegistry()
    service = RPModuleApplicationService(registry, gateway.rp_modules)
    snapshot = service.resolve_snapshot("s_forest001")

    with pytest.raises(ValueError, match="Duplicate RP module tool name"):
        registry.create_runtime(snapshot)


def test_snapshot_merges_story_and_session_config_with_story_capability_ceiling(tmp_path):
    gateway = get_data_service_gateway(tmp_path / "rp-module-selection.sqlite3")
    registry = RPModuleRegistry()
    service = RPModuleApplicationService(registry, gateway.rp_modules)
    weights = {
        "critical_success": 10,
        "success": 30,
        "success_with_cost": 30,
        "setback": 25,
        "critical_failure": 5,
    }
    gateway.rp_modules.upsert_story_module(
        "demo_workspace",
        1,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        enabled=True,
        config={"auto_adjudication_enabled": False, "weights": weights},
    )
    gateway.rp_modules.upsert_session_override(
        "s_forest001",
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        enabled=True,
        config={"auto_adjudication_enabled": True},
    )

    first = service.resolve_snapshot("s_forest001")
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

    gateway.rp_modules.upsert_story_module(
        "demo_workspace",
        1,
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        enabled=False,
        config={"auto_adjudication_enabled": False, "weights": weights},
    )
    second = service.resolve_snapshot("s_forest001")
    assert second.get(RP_MODULE_NARRATIVE_OUTCOME_NAME).effective_enabled is False
    assert first.get(RP_MODULE_NARRATIVE_OUTCOME_NAME).effective_enabled is True
    disabled_runtime = registry.create_runtime(second)
    assert "rp_story_outcome" not in [tool.name for tool in disabled_runtime.get_tools()]
    assert all(
        section.id != RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID
        for section in disabled_runtime.get_runtime_sections(
            ModuleContextRequest(session_id="s_forest001")
        )
    )


def test_dice_commands_follow_latest_story_mount_state(tmp_path):
    gateway = get_data_service_gateway(tmp_path / "rp-module-commands.sqlite3")
    registry = RPModuleRegistry()
    service = RPModuleApplicationService(registry, gateway.rp_modules)
    assert "/roll" in [item.name for item in service.get_commands("s_forest001")]

    gateway.rp_modules.upsert_story_module(
        "demo_workspace",
        1,
        RP_MODULE_DICE_NAME,
        enabled=False,
        config={},
    )
    names = [item.name for item in service.get_commands("s_forest001")]
    assert names == ["/rp_modules", "/rp_module"]


def test_application_service_owns_empty_override_and_story_capability_ceiling(
    tmp_path,
):
    gateway = get_data_service_gateway(tmp_path / "rp-module-application.sqlite3")
    service = RPModuleApplicationService(RPModuleRegistry(), gateway.rp_modules)

    overridden = service.patch_session_override(
        "s_forest001",
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        enabled=False,
        replace_enabled=True,
        config={},
    )
    assert (
        overridden.get(RP_MODULE_NARRATIVE_OUTCOME_NAME).effective_enabled
        is False
    )

    inherited = service.patch_session_override(
        "s_forest001",
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
        enabled=None,
        replace_enabled=True,
        config={},
    )
    assert inherited.get(RP_MODULE_NARRATIVE_OUTCOME_NAME).session_config == {}
    assert gateway.rp_modules.get_session_override(
        "s_forest001",
        RP_MODULE_NARRATIVE_OUTCOME_NAME,
    ) is None

    unmounted_story = gateway.catalog.create_story(
        "demo_workspace",
        title="未挂载剧情模块的隔离故事",
    )
    assert unmounted_story is not None
    unmounted_session = gateway.catalog.create_session(
        "demo_workspace",
        unmounted_story.id,
        session_id="s_unmounted_plot_module",
    )
    assert unmounted_session is not None
    with pytest.raises(ValueError, match="not mounted on Story"):
        service.patch_session_override(
            unmounted_session.id,
            RP_MODULE_PLOT_SCHEDULER_NAME,
            enabled=True,
            replace_enabled=True,
            config={},
        )
