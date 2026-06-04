"""SubAgentContext — 子 Agent 上下文容器。

类似主 Agent RPGContext 的 Fixed Layer 概念，为子 Agent 提供
系统提示 + 世界书 + 角色卡的轻量上下文，避免 OOC 判断。

Usage::

    # 直接构造
    ctx = SubAgentContext(
        system_prompt="You are the state table updater...",
        lorebook_entries=[{"name": "世界设定", "content": "..."}],
        characters=[{"name": "Alice", "content": "..."}],
    )
    system_text = ctx.render()

    # 从管理器工厂构建（自动读取已启用的条目）
    ctx = SubAgentContext.from_managers(
        system_prompt="...",
        character_mgr=character_mgr,
        lorebook_mgr=lorebook_mgr,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


class SubAgentContext:
    """子 Agent 上下文容器。

    将系统提示、世界书条目和角色卡合并为一段格式化的系统级文本，
    输出格式与 ``fixed_layer.jinja`` 模板一致。

    Parameters
    ----------
    system_prompt:
        系统提示文本。
    lorebook_entries:
        世界书条目列表，每项含 ``name``、``content``，可选 ``description``、``tags``。
    characters:
        角色卡列表，每项含 ``name``、``content``，可选 ``personality``、``details``。
    """

    def __init__(
        self,
        system_prompt: str = "",
        lorebook_entries: list[dict[str, Any]] | None = None,
        characters: list[dict[str, Any]] | None = None,
    ) -> None:
        self._system_prompt = system_prompt
        self._lorebook_entries = lorebook_entries or []
        self._characters = characters or []

    # ── public API ────────────────────────────────────────────────────

    def render(self) -> str:
        """渲染完整上下文：系统提示 + 世界书 + 角色卡。

        空段自动跳过（若无世界书条目则世界书段不出现）。
        """
        parts: list[str] = []

        if self._system_prompt.strip():
            parts.append(self._system_prompt.strip())

        lore_section = self._render_lorebook()
        if lore_section:
            parts.append(lore_section)

        char_section = self._render_characters()
        if char_section:
            parts.append(char_section)

        return "\n\n".join(parts)

    # ── factory ───────────────────────────────────────────────────────

    @classmethod
    def from_managers(
        cls,
        system_prompt: str,
        character_mgr: Any = None,
        lorebook_mgr: Any = None,
    ) -> SubAgentContext:
        """从管理器实时读取已启用的条目构建上下文。

        管理器可能为 ``None``（初始化失败时），此时对应数据段自动跳过。
        """
        lorebook_entries: list[dict[str, Any]] = []
        if lorebook_mgr is not None:
            try:
                lorebook_entries = lorebook_mgr.list_enabled_entries()
            except Exception:
                pass

        characters: list[dict[str, Any]] = []
        if character_mgr is not None:
            try:
                characters = character_mgr.list_enabled_characters()
            except Exception:
                pass

        return cls(
            system_prompt=system_prompt,
            lorebook_entries=lorebook_entries,
            characters=characters,
        )

    # ── internal renderers ────────────────────────────────────────────

    def _render_lorebook(self) -> str:
        """渲染世界书段落（与 lorebook.jinja 输出格式一致）。"""
        if not self._lorebook_entries:
            return ""

        lines: list[str] = ["## 世界书\n"]
        for entry in self._lorebook_entries:
            name = entry.get("name", "")
            lines.append(f"### {name}")
            desc = entry.get("description")
            if desc:
                lines.append(f"> {desc}")
            tags = entry.get("tags")
            if tags:
                lines.append(f"标签: {', '.join(tags)}")
            content = entry.get("content", "")
            if content:
                lines.append(content)
            lines.append("")

        return "\n".join(lines).rstrip()

    def _render_characters(self) -> str:
        """渲染角色卡段落（与 character_card.jinja 输出格式一致）。"""
        if not self._characters:
            return ""

        lines: list[str] = ["## 角色卡\n"]
        for char in self._characters:
            name = char.get("name", "")
            lines.append(f"### {name}")
            personality = char.get("personality")
            if personality:
                lines.append(f"个性: {personality}")
            content = char.get("content", "")
            if content:
                lines.append(content)
            details = char.get("details")
            if details:
                lines.append("**深层设定:**")
                for detail in details:
                    d_name = detail.get("name", "")
                    d_content = detail.get("content", "")
                    lines.append(f"- {d_name}: {d_content}")
            lines.append("")

        return "\n".join(lines).rstrip()
