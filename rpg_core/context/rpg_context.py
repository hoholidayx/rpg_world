"""RPGContext — typed 5-layer context container with unified access.

Each layer has a ``type`` tag for classification.  ``to_messages()`` flattens
to OpenAI-compatible ``list[dict]`` with ``type`` keys preserved (ignored by
the API, useful for middleware / logging).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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

    MILESTONES = "milestones"
    """[N+1] Milestones: active plot milestones."""

    STORY_MEMORY = "story_memory"
    """[N+2] Story Memory: accumulated character/plot details."""

    RECALLED_MEMORY = "recalled_memory"
    """[N+3] Recalled Memory: dynamically injected context items."""

    STATUS_TABLES = "status_tables"
    """[N+4] Status Tables: live game-state CSV data."""

    USER_MESSAGE = "user_message"
    """[N+5] User input (merged with before/after extensions)."""


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

    milestones: str | None = None
    """[N+1] Milestones — rendered milestone module."""

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

        self._add(msgs, "system", self.milestones, LayerType.MILESTONES)
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
            LayerType.MILESTONES: self.milestones,
            LayerType.STORY_MEMORY: self.story_memory,
            LayerType.RECALLED_MEMORY: self.recalled_memory,
            LayerType.STATUS_TABLES: self.status_tables,
        }
        return mapping.get(type_)

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
