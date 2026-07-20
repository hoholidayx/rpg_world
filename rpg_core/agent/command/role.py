"""Player-facing rendering and index resolution for ``/role_bind``."""

from __future__ import annotations

from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    PlayerCharacterOption,
    SessionPlayerCharacterState,
)


def render_role_bind_prompt(
    options: list[PlayerCharacterOption],
    state: SessionPlayerCharacterState,
    *,
    error: str = "",
) -> str:
    if not options:
        return "当前故事还没有可扮演角色。请先在角色库创建角色，并挂载到当前故事。"

    lines: list[str] = []
    if error.strip():
        lines.extend((error.strip(), ""))
    current_character_id = (
        state.player.character_id
        if state.status is PlayerCharacterBindingStatus.BOUND
        and state.player is not None
        else None
    )
    lines.append("请选择你要扮演的角色（回复 /role_bind 序号）：")
    for index, option in enumerate(options, start=1):
        marker = (
            "（当前扮演）"
            if option.snapshot.character_id == current_character_id
            else ""
        )
        lines.append(f"{index}. {option.snapshot.name}{marker}")
        lines.append(f"   {option.summary}")
    lines.extend(("", "示例：/role_bind 2"))
    return "\n".join(lines)


def resolve_role_index(
    options: list[PlayerCharacterOption],
    index: int,
) -> PlayerCharacterOption:
    if index < 1 or index > len(options):
        raise ValueError(f"无效角色序号: {index}")
    return options[index - 1]


__all__ = ["render_role_bind_prompt", "resolve_role_index"]
