"""RPG Context configuration — adjustable parameters for the 6-layer context builder."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtensionModuleDef:
    """定义一个可复用的拓展模块，可添加到动态拓展层或用户拓展层。

    Attributes:
        name: 模块标识符。
        template: Jinja 模板路径（相对 jinja/modules/）。
        position: 注入位置，仅用户拓展层有效 ("before" | "after")。
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
    summary_round_size: int = 100      # 每多少轮产生一个摘要块
    hot_history_rounds: int = 50       # 保留多少轮原始消息

    # ── 固定层开关 ──────────────────────────────────
    enable_character: bool = True
    enable_lorebook: bool = True
    enable_persistent_memory: bool = True

    # ── 摘要层开关 ──────────────────────────────────
    enable_summaries: bool = True

    # ── 动态层开关 ──────────────────────────────────
    enable_milestones: bool = True
    enable_realtime_memory: bool = True
    enable_status_tables: bool = True

    # ── 动态拓展层 — 插入 history 之后、user 输入之前 ─
    dynamic_extension: list[ExtensionModuleDef] = field(default_factory=lambda: [
        ExtensionModuleDef(name="attention_anchor", template="modules/attention_anchor.jinja"),
        ExtensionModuleDef(name="random_event", template="modules/random_event.jinja"),
    ])

    # ── 用户拓展层 — 注入到 user 消息内容前/后 ───────
    user_extension: list[ExtensionModuleDef] = field(default_factory=lambda: [
        ExtensionModuleDef(name="user_reply_prefix", template="modules/user_reply_prefix.jinja", position="before"),
        ExtensionModuleDef(name="user_reply_suffix", template="modules/user_reply_suffix.jinja", position="after"),
    ])
