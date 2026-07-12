from __future__ import annotations

import pytest

from rpg_data.services.gateway import DataServiceGateway
from rpg_data.story_template import (
    StoryTextTemplateError,
    render_story_text_template,
    validate_story_text_template,
)


def test_story_text_template_renders_allowlisted_player_name_once() -> None:
    rendered = render_story_text_template(
        "欢迎，{USER_PLAY_ROLE_NAME}。",
        user_play_role_name="Alice {UNKNOWN_ROLE}",
    )

    assert rendered == "欢迎，Alice {UNKNOWN_ROLE}。"


def test_story_text_template_supports_literal_escape() -> None:
    rendered = render_story_text_template(
        "变量写法：{{USER_PLAY_ROLE_NAME}}；实际：{USER_PLAY_ROLE_NAME}",
        user_play_role_name="Alice",
    )

    assert rendered == "变量写法：{USER_PLAY_ROLE_NAME}；实际：Alice"


def test_story_text_template_rejects_unknown_single_brace_variable() -> None:
    with pytest.raises(StoryTextTemplateError, match=r"\{UNKNOWN_ROLE\}"):
        validate_story_text_template("欢迎，{UNKNOWN_ROLE}。")


def test_story_text_template_leaves_non_variable_braces_unchanged() -> None:
    rendered = render_story_text_template(
        '示例 JSON：{"name":"Alice"}，集合：{alice,bob}',
        user_play_role_name="Alice",
    )

    assert rendered == '示例 JSON：{"name":"Alice"}，集合：{alice,bob}'


def test_catalog_rejects_unknown_story_variables_without_mutation() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        story = gateway.catalog.get_story("demo_workspace", 1)
        assert story is not None

        with pytest.raises(StoryTextTemplateError, match="UNKNOWN_ROLE"):
            gateway.catalog.update_story(
                "demo_workspace",
                story.id,
                story_prompt="玩家是 {UNKNOWN_ROLE}",
            )

        unchanged = gateway.catalog.get_story("demo_workspace", story.id)
        assert unchanged is not None
        assert unchanged.story_prompt == story.story_prompt
    finally:
        gateway.close()
