"""SubAgentContext — 子 Agent 上下文容器。

为子 Agent 提供世界书 + 角色卡的轻量上下文，避免 OOC 判断。
系统提示不在此维护，由 ``BaseSubAgent.bind_context()`` 在绑定时注入。

Usage::

    ctx = SubAgentContext(
        lorebook_entries=[{"name": "世界设定", "content": "..."}],
        characters=[{"name": "Alice", "content": "..."}],
    )
    system_text = ctx.render()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.context.fixed_layer.contributors import (
    annotate_player_character_cards,
    build_character_section,
    build_lorebook_section,
    build_player_character_section,
)
from rpg_core.context.fixed_layer.rendering import (
    render_fixed_layer_sections,
)

if TYPE_CHECKING:
    from rpg_core.context.fixed_layer.contributors.player_character import (
        PlayerCharacterContext,
    )


class SubAgentContext:
    """子 Agent 上下文容器。

    只维护世界书条目和角色卡数据，系统提示由 ``BaseSubAgent`` 在绑定时
    通过 ``set_system_prompt()`` 注入。输出格式与 ``fixed_layer.jinja``
    模板一致。

    Parameters
    ----------
    lorebook_entries:
        世界书条目列表，每项含 ``name``、``content``，可选 ``description``、``tags``。
    characters:
        角色卡列表，每项含 ``name``、``content``，可选 ``personality``、``details``。
    """

    def __init__(
        self,
        lorebook_entries: list[dict[str, object]] | None = None,
        characters: list[dict[str, object]] | None = None,
        player_character: "PlayerCharacterContext | None" = None,
    ) -> None:
        self._system_prompt: str = ""  # 由 bind_context() 注入
        self._lorebook_entries = lorebook_entries or []
        self._characters = characters or []
        self._player_character = player_character

    # ── public API ────────────────────────────────────────────────────

    def set_system_prompt(self, prompt: str) -> None:
        """设置子 Agent 自己的系统提示（由 BaseSubAgent.bind_context 调用）。"""
        self._system_prompt = prompt

    def render(
        self,
        *,
        player_character: "PlayerCharacterContext | None" = None,
    ) -> str:
        """渲染完整上下文：系统提示（子 Agent 自身） + 世界书 + 角色卡。

        空段自动跳过（若无世界书条目则世界书段不出现）。
        """
        parts: list[str] = []

        if self._system_prompt.strip():
            parts.append(self._system_prompt.strip())

        lore_section = self._render_lorebook()
        if lore_section:
            parts.append(lore_section)

        resolved_player = player_character or self._player_character
        player_section = self._render_player_character(resolved_player)
        if player_section:
            parts.append(player_section)

        char_section = self._render_characters(resolved_player)
        if char_section:
            parts.append(char_section)

        return "\n\n".join(parts)

    # ── internal renderers ────────────────────────────────────────────

    def _render_lorebook(self) -> str:
        """渲染世界书段落。"""
        section = build_lorebook_section(self._lorebook_entries)
        return render_fixed_layer_sections([section]) if section is not None else ""

    def _render_player_character(
        self,
        player_character: "PlayerCharacterContext | None",
    ) -> str:
        section = build_player_character_section(player_character)
        return render_fixed_layer_sections([section]) if section is not None else ""

    def _render_characters(
        self,
        player_character: "PlayerCharacterContext | None",
    ) -> str:
        """渲染角色卡段落。"""
        section = build_character_section(
            annotate_player_character_cards(
                self._characters,
                player_character,
            )
        )
        return render_fixed_layer_sections([section]) if section is not None else ""
