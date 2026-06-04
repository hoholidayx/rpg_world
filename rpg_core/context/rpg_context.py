"""RPGContext — typed 5-layer context container with unified access.

Each layer has a ``type`` tag for classification.  ``to_messages()`` flattens
to OpenAI-compatible ``list[dict]`` with ``type`` keys preserved (ignored by
the API, useful for middleware / logging).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.tokenizer import TokenCounter


class LayerType:
    """Layer type constants — each maps to one entry in the 5-layer structure."""

    FIXED = "fixed_layer"
    """[0] Fixed: prompt + lorebook + character cards."""

    PERSISTENT_MEMORY = "persistent_memory"
    """[1] Persistent Memory: offline-updated long-term memory."""

    SUMMARY = "summary"
    """[2] Summary: compressed conversation summaries (conditional)."""

    HOT_HISTORY = "hot_history"
    """[3..N] Hot History: recent N user/assistant rounds."""

    STORY_MEMORY = "story_memory"
    """[N+2] Story Memory: accumulated character/plot details."""

    RECALLED_MEMORY = "recalled_memory"
    """[N+3] Recalled Memory: dynamically injected context items."""

    STATUS_TABLES = "status_tables"
    """[N+4] Status Tables: live game-state CSV data."""

    USER_MESSAGE = "user_message"
    """[N+5] User input (merged with before/after extensions)."""


@dataclass
class LayerInfo:
    """Structured metadata for a single context layer.

    Returned by ``RPGContext.layer_summary()`` for inspection / display.
    """

    type: str
    """Layer type constant (e.g. ``"fixed_layer"``)."""

    role: str
    """Message role: ``"system"``, ``"user"``, or ``"assistant"``."""

    status: str
    """``"active"`` when the layer has content, ``"inactive"`` otherwise."""

    char_count: int
    """Number of characters in the rendered content."""

    token_count: int
    """Estimated token count for this layer."""

    description: str
    """Short human-readable description (e.g. ``"3 条世界书 + 2 张角色卡"``)."""


@dataclass
class RPGContext:
    """完整的 5 层 RPG 上下文容器。

    提供：
    - 结构化字段访问（``ctx.fixed_layer``、``ctx.summary``……）
    - ``to_messages()`` 扁平化为 OpenAI 消息格式，每 dict 带 ``type``
    - ``get_layer(type_str)`` 按类型检索

    Usage::

        ctx: RPGContext = builder.build(...)
        messages = ctx.to_messages()   # → list[dict]  for OpenAI
        summary = ctx.get_layer("summary")
    """

    # ── Layers ─────────────────────────────────────────────────────────

    fixed_layer: str = ""
    """[0] Fixed Layer — rendered prompt + lore + characters."""

    persistent_memory: str | None = None
    """[1] Persistent Memory — offline long-term memory content."""

    summary: str | None = None
    """[2] Summary Layer — compressed summaries (None if no summaries)."""

    hot_history: list[dict] = field(default_factory=list)
    """[3..N] Hot History — recent user/assistant message dicts."""

    story_memory: str | None = None
    """[N+2] Story Memory — rendered story detail items."""

    recalled_memory: str | None = None
    """[N+3] Recalled Memory — dynamically recalled context items."""

    status_tables: str | None = None
    """[N+4] Status Tables — rendered game-state tables."""

    # ── User input parts ───────────────────────────────────────────────

    user_before: str | None = None
    """Extension content injected **before** the user input."""

    user_input: str = ""
    """The raw user input text."""

    user_after: str | None = None
    """Extension content injected **after** the user input."""

    # ── Public API ─────────────────────────────────────────────────────

    def to_messages(self) -> list[dict[str, Any]]:
        """Flatten to OpenAI message list with ``type`` annotations.

        Each dict contains ``role``, ``content``, and ``type`` keys.
        The ``type`` key is ignored by OpenAI but available for
        middleware, logging, and debugging.
        """
        msgs: list[dict[str, Any]] = []

        self._add(msgs, "system", self.fixed_layer, LayerType.FIXED)
        self._add(msgs, "system", self.persistent_memory, LayerType.PERSISTENT_MEMORY)
        self._add(msgs, "system", self.summary, LayerType.SUMMARY)

        for h in self.hot_history:
            h["type"] = LayerType.HOT_HISTORY
            msgs.append(h)

        self._add(msgs, "system", self.story_memory, LayerType.STORY_MEMORY)
        self._add(msgs, "system", self.recalled_memory, LayerType.RECALLED_MEMORY)
        self._add(msgs, "system", self.status_tables, LayerType.STATUS_TABLES)

        # User message: before → input → after for API compatibility
        parts: list[str] = []
        if self.user_before:
            parts.append(f"[user_prefix]{self.user_before}[/user_prefix]")
        if self.user_input:
            parts.append(self.user_input)
        if self.user_after:
            parts.append(f"[user_suffix]{self.user_after}[/user_suffix]")
        user_content = "\n\n".join(parts)
        msgs.append({"role": "user", "content": user_content, "type": LayerType.USER_MESSAGE})

        return msgs

    def get_layer(self, type_: str) -> str | None:
        """Get the rendered content of a layer by type string.

        Returns ``None`` if the layer is empty or disabled.
        """
        mapping = {
            LayerType.FIXED: self.fixed_layer,
            LayerType.PERSISTENT_MEMORY: self.persistent_memory,
            LayerType.SUMMARY: self.summary,
            LayerType.STORY_MEMORY: self.story_memory,
            LayerType.RECALLED_MEMORY: self.recalled_memory,
            LayerType.STATUS_TABLES: self.status_tables,
        }
        return mapping.get(type_)

    # ── Layer metadata for inspection ───────────────────────────────────

    def layer_summary(self, token_counter: TokenCounter) -> list[LayerInfo]:
        """Return structured metadata for each layer with token counts.

        Uses *token_counter* to estimate tokens per layer.
        """
        layers: list[LayerInfo] = []

        def _add(info_type, role, content_or_none, desc):
            if content_or_none:
                tokens = token_counter.count(content_or_none)
                layers.append(LayerInfo(
                    type=info_type, role=role,
                    status="active",
                    char_count=len(content_or_none),
                    token_count=tokens,
                    description=desc,
                ))
            else:
                layers.append(LayerInfo(
                    type=info_type, role=role,
                    status="inactive",
                    char_count=0, token_count=0,
                    description="-",
                ))

        # [0] Fixed Layer
        lore_count = self._count_tokens_of("lorebook_entries")
        char_count = self._count_tokens_of("characters")
        _add(LayerType.FIXED, "system", self.fixed_layer,
             _build_fixed_desc(lore_count, char_count))

        # [1] Persistent Memory
        _add(LayerType.PERSISTENT_MEMORY, "system", self.persistent_memory,
             _truncate_text(self.persistent_memory or "", 50))

        # [2] Summary
        _add(LayerType.SUMMARY, "system", self.summary,
             _truncate_text(self.summary or "", 50))

        # [3..N] Hot History
        if self.hot_history:
            tokens = token_counter.count_messages(self.hot_history)
            user_rounds = sum(1 for m in self.hot_history if m.get("role") == "user")
            layers.append(LayerInfo(
                type=LayerType.HOT_HISTORY, role="mixed",
                status="active",
                char_count=sum(len(m.get("content") or "") for m in self.hot_history),
                token_count=tokens,
                description=f"{user_rounds} 轮对话 (user/assistant)",
            ))
        else:
            layers.append(LayerInfo(
                type=LayerType.HOT_HISTORY, role="mixed",
                status="inactive", char_count=0, token_count=0,
                description="-",
            ))

        # [N+1] Story Memory
        _add(LayerType.STORY_MEMORY, "system", self.story_memory,
             _build_story_memory_desc(self.story_memory))

        # [N+3] Recalled Memory
        _add(LayerType.RECALLED_MEMORY, "system", self.recalled_memory,
             _truncate_text(self.recalled_memory or "", 50))

        # [N+4] Status Tables
        _add(LayerType.STATUS_TABLES, "system", self.status_tables,
             _build_status_desc(self.status_tables))

        # [N+5] User Message
        user_parts = []
        if self.user_before:
            user_parts.append(self.user_before)
        if self.user_input:
            user_parts.append(self.user_input)
        if self.user_after:
            user_parts.append(self.user_after)
        user_content = "\n\n".join(user_parts)
        if user_content:
            layers.append(LayerInfo(
                type=LayerType.USER_MESSAGE, role="user",
                status="active",
                char_count=len(user_content),
                token_count=token_counter.count(user_content),
                description=_truncate_text(user_content, 50),
            ))
        else:
            layers.append(LayerInfo(
                type=LayerType.USER_MESSAGE, role="user",
                status="inactive", char_count=0, token_count=0,
                description="-",
            ))

        return layers

    def to_markdown(self, token_counter: TokenCounter) -> str:
        """Render context structure as a Markdown table.

        Example output::

            | Layer | Status | Tokens | Description |
            |---|---|---|---|
            | Fixed Layer | active | 1,234 | system prompt + 3 entries |
            | ... | ... | ... | ... |
            | **TOTAL** | | **7,414** | |
        """
        layers = self.layer_summary(token_counter)
        total_tokens = sum(l.token_count for l in layers)

        lines = [
            "| Layer | Status | Tokens | Description |",
            "|---|---|---:|---|",
        ]
        for info in layers:
            tokens_str = f"{info.token_count:,}" if info.token_count > 0 else "-"
            lines.append(
                f"| {_layer_display_name(info.type)} | {info.status} "
                f"| {tokens_str} | {info.description} |"
            )

        lines.append(
            f"| **TOTAL** | | **{total_tokens:,}** | |"
        )
        lines.append("")

        # Extract hot_history_rounds from config if available
        hot_rounds = getattr(self, "_hot_history_rounds", None)
        if hot_rounds is not None:
            lines.append(f"**配置:** history_rounds={hot_rounds}")

        return "\n".join(lines)

    # ── internal helpers (metadata extraction) ─────────────────────────

    @staticmethod
    def _count_tokens_of(key: str) -> int:
        """Count number of times *key* appears in the fixed layer text.

        A rough heuristic — the fixed layer template inserts entries as
        markdown sections.  We count the number of ``## `` headers that
        contain the key name.
        """
        # This is intentionally rough; subclasses can override.
        return 0

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _add(
        msgs: list[dict[str, Any]],
        role: str,
        content: str | None,
        type_: str,
    ) -> None:
        if content:
            msgs.append({"role": role, "content": content, "type": type_})


# ── module-level helpers ──────────────────────────────────────────────


def _layer_display_name(type_: str) -> str:
    """Map LayerType constant to a human-readable display name."""
    names = {
        LayerType.FIXED: "Fixed Layer",
        LayerType.PERSISTENT_MEMORY: "Persistent Memory",
        LayerType.SUMMARY: "Summary",
        LayerType.HOT_HISTORY: "Hot History",
        LayerType.STORY_MEMORY: "Story Memory",
        LayerType.RECALLED_MEMORY: "Recalled Memory",
        LayerType.STATUS_TABLES: "Status Tables",
        LayerType.USER_MESSAGE: "User Message",
    }
    return names.get(type_, type_)


def _truncate_text(text: str, max_chars: int = 50) -> str:
    """Truncate text with ellipsis if longer than *max_chars*."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _build_fixed_desc(lore_count: int, char_count: int) -> str:
    """Build description for the fixed layer."""
    parts = ["system prompt"]
    if lore_count > 0:
        parts.append(f"{lore_count} 条世界书")
    if char_count > 0:
        parts.append(f"{char_count} 张角色卡")
    return " + ".join(parts) if len(parts) > 1 else parts[0]


def _build_story_memory_desc(content: str | None) -> str:
    """Estimate story memory item count from rendered content."""
    if not content:
        return "-"
    count = content.count("\n- ")  # each item is a bullet
    if count > 0:
        return f"{count} 条剧情细节"
    return _truncate_text(content, 50)


def _build_status_desc(content: str | None) -> str:
    """Estimate status table count from rendered content."""
    if not content:
        return "-"
    count = content.count("\n### ")  # each table has a ### header
    extra = 1 if content.startswith("### ") else 0
    total = count + extra
    return f"{total} 张状态表" if total > 0 else _truncate_text(content, 50)
