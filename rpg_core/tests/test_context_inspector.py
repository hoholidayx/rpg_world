from __future__ import annotations

import pytest

import rpg_core.context.renderer as renderer_module
from rpg_core.context.fixed_layer import FixedLayerSection
from rpg_core.context.fixed_layer.contributors import CoreRPContractContributor, StaticFixedLayerContributor
from rpg_core.context.inspector import ContextInspector
from rpg_core.context.rpg_context import (
    FixedLayerData,
    HotHistoryLayer,
    LayerType,
    Message,
    RecalledMemoryLayer,
    RPGContext,
    RPModuleRuntimeSection,
    RPModulesLayer,
    Role,
    StatusTablesLayer,
    StoryMemoryLayer,
    UserMessageLayer,
)
from rpg_core.context.usage import ContextPreviewUsagePayload, TurnUsageWirePayload
from rpg_core.rp_module_constants import RP_MODULE_DICE_SECTION_ID, RP_MODULE_DICE_SOURCE


def _fake_render(template_name: str, **context: object) -> str:
    if template_name == "layers/fixed_layer.jinja":
        section_ids = ",".join(section.id for section in context["fixed_sections"])
        return f"fixed|{section_ids}"
    if template_name == "layers/user_message.jinja":
        return context["user_input"]
    return template_name


@pytest.fixture(autouse=True)
def _patch_renderer(monkeypatch):
    monkeypatch.setattr(renderer_module, "render_jinja_template", _fake_render)


def test_context_inspector_markdown_includes_history_stats(fake_token_counter):
    ctx = RPGContext(
        fixed_layer=FixedLayerData(
            sections=[FixedLayerSection(id="core", title="核心", content="fixed")],
            lorebook_entries=[{"name": "Lore"}],
            characters=[{"name": "Alice"}],
        ),
        hot_history=HotHistoryLayer(messages=[
            Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
            Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
            Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        ]),
    )

    md = ContextInspector(ctx, fake_token_counter, hot_history_rounds=5).to_markdown()

    assert "## 上下文概览" in md
    assert "## 分层明细" in md
    assert "Fixed Layer" in md
    assert "历史消息: **3** 条" in md
    assert "历史轮数: **2** 轮" in md
    assert "历史窗口: **5** 轮" in md
    assert "user 2, assistant 1, tool 0, system 0" in md
    assert "1 条世界书" in md
    assert "1 张角色卡" in md


def test_context_inspector_handles_hot_history_without_user_anchor(fake_token_counter):
    ctx = RPGContext(
        fixed_layer=FixedLayerData(sections=[FixedLayerSection(id="core", title="核心", content="fixed")]),
        hot_history=HotHistoryLayer(messages=[
            Message(Role.ASSISTANT, "a1"),
            Message(Role.TOOL, "tool1"),
            Message(Role.SYSTEM, "sys1"),
        ]),
        user_message=UserMessageLayer(user_input="hi"),
    )

    summary = ContextInspector(ctx, fake_token_counter).layer_summary()

    assert summary[3].description == "2 轮 / 3 条 (user=0, assistant=1, tool=1, system=1)"
    assert summary[-1].type == "user_message"
    assert summary[-1].status == "active"


def test_context_inspector_verbose_log_omits_history_content(fake_token_counter):
    ctx = RPGContext(
        fixed_layer=FixedLayerData(
            sections=[FixedLayerSection(id="core", title="核心", content="fixed")]
        ),
        hot_history=HotHistoryLayer(messages=[
            Message(Role.USER, "history user secret", turn_id=1, seq_in_turn=1),
            Message(Role.ASSISTANT, "history assistant secret", turn_id=1, seq_in_turn=2),
        ]),
        user_message=UserMessageLayer(user_input="current input"),
    )

    log = ContextInspector(ctx, fake_token_counter).to_verbose_log()

    assert "当前 Context（结构化分层）" in log
    assert "fixed_layer (system)" in log
    assert "fixed|core" in log
    assert "hot_history (mixed)" in log
    assert "turns=1" in log
    assert "history user secret" not in log
    assert "history assistant secret" not in log
    assert "user_message (user)" in log
    assert "current input" in log


def test_context_inspector_uses_provider_dynamic_layer_order(fake_token_counter):
    ctx = RPGContext(
        story_memory=StoryMemoryLayer(details=[{"text": "story"}]),
        status_tables=StatusTablesLayer(tables=[{"name": "status"}]),
        recalled_memory=RecalledMemoryLayer(items=["recall"]),
        rp_modules=RPModulesLayer(
            sections=[RPModuleRuntimeSection(id="runtime", title="运行态", content="state")]
        ),
    )
    inspector = ContextInspector(ctx, fake_token_counter)

    layer_types = [layer.type for layer in inspector.layer_summary()]
    assert layer_types[4:8] == [
        LayerType.STORY_MEMORY,
        LayerType.STATUS_TABLES,
        LayerType.RECALLED_MEMORY,
        LayerType.RP_MODULES,
    ]

    verbose = inspector.to_verbose_log()
    assert verbose.index("story_memory (system)") < verbose.index("status_tables (system)")
    assert verbose.index("status_tables (system)") < verbose.index("recalled_memory (system)")
    assert verbose.index("recalled_memory (system)") < verbose.index("rp_modules (system)")


def test_context_inspector_payload_includes_rendered_layers_and_messages(fake_token_counter):
    ctx = RPGContext(
        fixed_layer=FixedLayerData(sections=[FixedLayerSection(id="core", title="核心", content="fixed")]),
        hot_history=HotHistoryLayer(messages=[
            Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
            Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        ]),
        user_message=UserMessageLayer(user_input="inspect"),
    )

    payload = ContextInspector(ctx, fake_token_counter, hot_history_rounds=3, context_limit=10).to_payload(session_id="s1")

    assert payload["formatVersion"] == "context-preview.v1"
    assert payload["sessionId"] == "s1"
    assert payload["hotHistoryRounds"] == 3
    assert payload["totals"] == {
        "layerCount": 9,
        "activeLayers": 3,
        "tokenCount": 5,
        "messageCount": 4,
    }
    assert payload["usageEstimate"]["usedTokens"] == 5
    assert payload["usageEstimate"]["contextLimit"] == 10
    assert payload["usageEstimate"]["source"] == "context_preview"
    assert payload["usageEstimate"]["accuracy"] == "estimated"
    assert "ratio" not in payload["usageEstimate"]
    assert "status" not in payload["usageEstimate"]

    layers = payload["layers"]
    fixed = layers[0]
    assert fixed["index"] == 0
    assert fixed["type"] == LayerType.FIXED
    assert fixed["role"] == Role.SYSTEM.value
    assert fixed["status"] == "active"
    assert fixed["content"] == "fixed|core"

    summary = layers[2]
    assert summary["type"] == LayerType.SUMMARY
    assert summary["status"] == "inactive"
    assert summary["content"] == ""

    hot_history = layers[3]
    assert hot_history["type"] == LayerType.HOT_HISTORY
    assert hot_history["description"] == "1 轮 / 2 条 (user=1, assistant=1, tool=0, system=0)"
    assert "[user]\nu1" in hot_history["content"]
    assert "[assistant]\na1" in hot_history["content"]

    messages = payload["messages"]
    assert messages == [
        {"role": "system", "content": "fixed|core"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "inspect"},
    ]


def test_context_preview_token_estimate_counts_final_messages():
    class FinalMessageCounter:
        def count(self, text: str) -> int:
            return len(text)

        def count_messages(self, messages: list[Message]) -> int:
            assert [message.content for message in messages] == ["fixed|core", "u1"]
            return 123

    ctx = RPGContext(
        fixed_layer=FixedLayerData(
            sections=[FixedLayerSection(id="core", title="核心", content="fixed")]
        ),
        user_message=UserMessageLayer(user_input="u1"),
    )

    payload = ContextInspector(ctx, FinalMessageCounter()).to_payload(session_id="s1")

    assert payload["totals"]["tokenCount"] == 123
    assert payload["usageEstimate"]["usedTokens"] == 123


def test_usage_payload_views_normalize_transport_shapes():
    turn_usage = TurnUsageWirePayload.from_payload({
        "prompt_tokens": "12",
        "completionTokens": 4,
        "total_tokens": 16,
        "cachedTokens": "3",
        "source": "provider_usage",
        "accuracy": "accurate",
        "model": "deepseek-test",
    })

    assert turn_usage is not None
    assert turn_usage.prompt_tokens == 12
    assert turn_usage.completion_tokens == 4
    assert turn_usage.total_tokens == 16
    assert turn_usage.cached_tokens == 3
    assert turn_usage.source == "provider_usage"
    assert turn_usage.accuracy == "accurate"
    assert turn_usage.model == "deepseek-test"

    preview_usage = ContextPreviewUsagePayload.from_payload({
        "usageEstimate": {
            "usedTokens": "128",
            "contextLimit": 1000000,
            "source": "context_preview",
            "accuracy": "estimated",
        },
        "totals": {"tokenCount": "128"},
    })

    assert preview_usage is not None
    assert preview_usage.used_tokens == 128
    assert preview_usage.context_limit == 1000000
    assert preview_usage.token_count == 128
    assert preview_usage.source == "context_preview"
    assert preview_usage.accuracy == "estimated"
    assert TurnUsageWirePayload.from_payload(None) is None
    assert ContextPreviewUsagePayload.from_payload({}) is None


def test_core_contributor_can_be_combined_with_static_module_sections():
    static_contributor = StaticFixedLayerContributor([
        FixedLayerSection(
            id=RP_MODULE_DICE_SECTION_ID,
            title="骰子模块",
            content="遇到需要随机裁定的结果时，使用 rp_dice_roll 工具。",
            priority=50,
            source=RP_MODULE_DICE_SOURCE,
        )
    ])

    sections = [
        *CoreRPContractContributor("测试世界").get_fixed_contribution().sections,
        *static_contributor.get_fixed_contribution().sections,
    ]
    sections = sorted(sections, key=lambda section: (section.priority, section.id))

    assert [section.id for section in sections] == ["core_rp_contract", RP_MODULE_DICE_SECTION_ID]
    assert "测试世界" in sections[0].content
    assert "rp_dice_roll" in sections[1].content
