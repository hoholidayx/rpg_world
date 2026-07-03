from __future__ import annotations

from rpg_core.context.rendering import render_jinja_template


def test_lorebook_template_wraps_content_in_bracket_tag():
    rendered = render_jinja_template(
        "modules/lorebook.jinja",
        lorebook_entries=[{
            "name": "炎心之木",
            "description": "与火焰符文和最初的燃烧有关的核心传说。",
            "tags": ["history", "magic"],
            "content": "北境森林传说中的世界之树。",
        }],
    )

    assert rendered.startswith("[lorebook]\n## 世界书")
    assert "### 炎心之木" in rendered
    assert "标签: history, magic" in rendered
    assert rendered.endswith("[/lorebook]")


def test_character_template_wraps_content_in_bracket_tag():
    rendered = render_jinja_template(
        "modules/character_card.jinja",
        characters=[{
            "name": "Alice",
            "personality": "curious",
            "content": "A young wizard.",
            "details": [{"name": "外貌", "content": "银白色长发。"}],
        }],
    )

    assert rendered.startswith("[character_card]\n## 角色卡")
    assert "### Alice" in rendered
    assert "个性: curious" in rendered
    assert "- 外貌: 银白色长发。" in rendered
    assert rendered.endswith("[/character_card]")
