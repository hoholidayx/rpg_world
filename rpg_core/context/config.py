"""RPG Context configuration — adjustable parameters for the 5-layer context builder."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtensionModuleDef:
    """定义一个可复用的拓展模块，注入到 user 消息内容前/后。

    Attributes:
        name: 模块标识符。
        template: Jinja 模板路径（相对 jinja/modules/）。
        position: 注入位置 ("before" | "after")。
        enabled: 是否启用。
    """

    name: str
    template: str
    position: str = "before"
    enabled: bool = True


@dataclass
class RPGContextConfig:
    """RPG 上下文构建器的可调节参数。"""

    # ── 窗口控制 ────────────────────────────────────
    hot_history_rounds: int = 50       # 保留多少轮原始消息

    # ── 固定层开关 ──────────────────────────────────
    enable_character: bool = True
    enable_lorebook: bool = True
    enable_persistent_memory: bool = True

    # ── 摘要层开关 ──────────────────────────────────
    enable_summaries: bool = True

    # ── 动态层开关 ──────────────────────────────────
    enable_story_memory: bool = True
    enable_recalled_memory: bool = True
    enable_status_tables: bool = True

    # ── 用户拓展层 — 注入到 user 消息内容前/后 ───────
    user_extension: list[ExtensionModuleDef] = field(default_factory=lambda: [
        ExtensionModuleDef(name="user_reply_prefix", template="modules/user_reply_prefix.jinja", position="before"),
        ExtensionModuleDef(name="user_reply_suffix", template="modules/user_reply_suffix.jinja", position="after"),
    ])
