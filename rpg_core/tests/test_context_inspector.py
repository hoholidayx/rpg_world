from __future__ import annotations

import pytest

import rpg_core.context.renderer as renderer_module
from rpg_core.context.fixed_layer import FixedLayerComposer, FixedLayerSection
from rpg_core.context.inspector import ContextInspector
from rpg_core.context.rpg_context import (
    FixedLayerData,
    HotHistoryLayer,
    Message,
    RPGContext,
    Role,
    UserMessageLayer,
)


def _fake_render(template_name: str, **context: object) -> str:
    if template_name == "layers/fixed_layer.jinja":
        section_ids = ",".join(section.id for section in context["fixed_sections"])
        return f"fixed|{section_ids}|{len(context['lorebook_entries'])}|{len(context['characters'])}"
    if template_name == "layers/user_message.jinja":
        return context["user_input"]
    return template_name


@pytest.fixture(autouse=True)
def _patch_renderer(monkeypatch):
    monkeypatch.setattr(renderer_module, "render_jinja_template", _fake_render)


def test_context_inspector_markdown_includes_history_stats(fake_token_counter):
    ctx = RPGContext(
        fixed_layer=FixedLayerData(sections=[FixedLayerSection(id="core", title="核心", content="fixed")]),
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


def test_fixed_layer_composer_accepts_static_module_sections():
    composer = FixedLayerComposer("测试世界").with_module_sections([
        FixedLayerSection(
            id="rp_module_dice",
            title="骰子模块",
            content="遇到需要随机裁定的结果时，使用 rp_dice_roll 工具。",
            priority=50,
            source="rp_module:dice",
        )
    ])

    sections = composer.sections

    assert [section.id for section in sections] == ["core_rp_contract", "rp_module_dice"]
    assert "测试世界" in sections[0].content
    assert "rp_dice_roll" in sections[1].content
