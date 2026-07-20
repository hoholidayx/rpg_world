"""Story-domain policies shared by catalog and session applications."""

from rpg_core.story.template import (
    SUPPORTED_STORY_TEXT_VARIABLES,
    StoryTextTemplateError,
    UNBOUND_PLAYER_ROLE_NAME,
    USER_PLAY_ROLE_NAME,
    render_story_text_template,
    validate_story_text_template,
)

__all__ = [
    "SUPPORTED_STORY_TEXT_VARIABLES",
    "StoryTextTemplateError",
    "UNBOUND_PLAYER_ROLE_NAME",
    "USER_PLAY_ROLE_NAME",
    "render_story_text_template",
    "validate_story_text_template",
]
