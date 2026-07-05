from __future__ import annotations

from rpg_core.agent.sub_agents.context import SubAgentContext
from rpg_core.context.fixed_layer.contributors import (
    build_character_section,
    build_lorebook_section,
)
from rpg_core.context.fixed_layer.rendering import (
    render_fixed_layer_sections,
)
from rpg_core.context.rendering import render_jinja_template


def test_lorebook_template_renders_body_content():
    rendered = render_jinja_template(
        "modules/lorebook.jinja",
        lorebook_entries=[{
            "name": "炎心之木",
            "description": "与火焰符文和最初的燃烧有关的核心传说。",
            "tags": ["history", "magic"],
            "content": "北境森林传说中的世界之树。",
        }],
    )

    assert rendered.startswith("### 炎心之木")
    assert "### 炎心之木" in rendered
    assert "标签: history, magic" in rendered
    assert "[lorebook]" not in rendered


def test_character_template_renders_body_content():
    rendered = render_jinja_template(
        "modules/character_card.jinja",
        characters=[{
            "name": "Alice",
            "personality": "curious",
            "content": "A young wizard.",
            "details": [{"name": "外貌", "content": "银白色长发。"}],
        }],
    )

    assert rendered.startswith("### Alice")
    assert "### Alice" in rendered
    assert "个性: curious" in rendered
    assert "- 外貌: 银白色长发。" in rendered
    assert "[character_card]" not in rendered


def test_fixed_layer_sections_wrap_rendered_knowledge_sections():
    lorebook_section = build_lorebook_section([{
        "name": "炎心之木",
        "description": "与火焰符文和最初的燃烧有关的核心传说。",
        "tags": ["history", "magic"],
        "content": "北境森林传说中的世界之树。",
    }])
    character_section = build_character_section([{
        "name": "Alice",
        "personality": "curious",
        "content": "A young wizard.",
        "details": [{"name": "外貌", "content": "银白色长发。"}],
    }])
    assert lorebook_section is not None
    assert character_section is not None

    rendered = render_fixed_layer_sections([lorebook_section, character_section])

    assert rendered.startswith("[lorebook]\n# 世界书")
    assert "[/lorebook]" in rendered
    assert "[character_card]\n# 角色卡" in rendered
    assert rendered.index("[/lorebook]") < rendered.index("[character_card]\n# 角色卡")
    assert "### 炎心之木" in rendered
    assert "### Alice" in rendered


def test_sub_agent_context_reuses_fixed_layer_knowledge_sections():
    rendered = SubAgentContext(
        lorebook_entries=[{
            "name": "炎心之木",
            "description": "与火焰符文和最初的燃烧有关的核心传说。",
            "tags": ["history", "magic"],
            "content": "北境森林传说中的世界之树。",
        }],
        characters=[{
            "name": "Alice",
            "personality": "curious",
            "content": "A young wizard.",
            "details": [{"name": "外貌", "content": "银白色长发。"}],
        }],
    ).render()

    assert "[lorebook]\n# 世界书" in rendered
    assert "[character_card]\n# 角色卡" in rendered
    assert "### 炎心之木" in rendered
    assert "### Alice" in rendered
