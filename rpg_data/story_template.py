"""Safe, allowlisted rendering for Story-authored text templates."""

from __future__ import annotations

from collections.abc import Mapping

USER_PLAY_ROLE_NAME = "USER_PLAY_ROLE_NAME"
UNBOUND_PLAYER_ROLE_NAME = "尚未绑定玩家角色"

SUPPORTED_STORY_TEXT_VARIABLES = frozenset({USER_PLAY_ROLE_NAME})

__all__ = [
    "SUPPORTED_STORY_TEXT_VARIABLES",
    "StoryTextTemplateError",
    "UNBOUND_PLAYER_ROLE_NAME",
    "USER_PLAY_ROLE_NAME",
    "render_story_text_template",
    "validate_story_text_template",
]


class StoryTextTemplateError(ValueError):
    """Raised when Story text contains an unsupported template variable."""


def validate_story_text_template(template: str) -> None:
    """Validate a Story text template without evaluating or mutating it."""

    _render_template(str(template or ""), values=None)


def render_story_text_template(
    template: str,
    *,
    user_play_role_name: str,
) -> str:
    """Render supported variables once using plain-text substitution."""

    return _render_template(
        str(template or ""),
        values={USER_PLAY_ROLE_NAME: str(user_play_role_name)},
    )


def _render_template(
    template: str,
    *,
    values: Mapping[str, str] | None,
) -> str:
    rendered: list[str] = []
    index = 0
    length = len(template)

    while index < length:
        if template.startswith("{{", index):
            escaped_end = template.find("}}", index + 2)
            if escaped_end >= 0:
                escaped_name = template[index + 2:escaped_end]
                if _is_template_identifier(escaped_name):
                    rendered.append("{" + escaped_name + "}")
                    index = escaped_end + 2
                    continue

        if template[index] == "{":
            token_end = template.find("}", index + 1)
            if token_end >= 0:
                variable_name = template[index + 1:token_end]
                if _is_template_identifier(variable_name):
                    if variable_name not in SUPPORTED_STORY_TEXT_VARIABLES:
                        raise StoryTextTemplateError(
                            f"不支持的 Story 模板变量: {{{variable_name}}}"
                        )
                    rendered.append(
                        "{" + variable_name + "}"
                        if values is None
                        else values[variable_name]
                    )
                    index = token_end + 1
                    continue

        rendered.append(template[index])
        index += 1

    return "".join(rendered)


def _is_template_identifier(value: str) -> bool:
    if not value or not ("A" <= value[0] <= "Z"):
        return False
    return all(
        character == "_"
        or "0" <= character <= "9"
        or "A" <= character <= "Z"
        for character in value
    )
