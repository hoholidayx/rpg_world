"""RPGContext — typed 5-layer context container with unified access.

Each layer has a ``type`` tag for classification.  Messages flow through
the pipeline as ``Message`` objects; dict conversion only happens at the
LLM provider boundary (``Message.to_dict()``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_world.rpg_core.utils.tokenizer import TokenCounter


class Role(StrEnum):
    """Message role constants — eliminates hardcoded role strings."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


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


class MsgKey:
    """Message dict field-name constants, avoids magic strings."""

    ROLE = "role"
    CONTENT = "content"
    RP_HIS_ID = "rp_his_id"


class Message:
    """Typed wrapper for OpenAI-compatible message dicts.

    Eliminates hardcoded string keys throughout the pipeline.
    Convert to dict only at the LLM boundary via ``to_dict()``.
    """

    __slots__ = ("_role", "_content", "_rp_his_id", "_tool_call_id", "_tool_calls")

    def __init__(
        self,
        role: Role | str,
        content: str,
        rp_his_id: int = 0,
        tool_call_id: str = "",
        tool_calls: list[dict] | None = None,
    ) -> None:
        self._role = Role(role) if isinstance(role, str) else role
        self._content = content
        self._rp_his_id = rp_his_id
        self._tool_call_id = tool_call_id
        self._tool_calls = tool_calls or None

    @property
    def role(self) -> Role:
        """Message role as a ``Role`` enum — never a raw string."""
        return self._role

    @property
    def content(self) -> str:
        return self._content

    @property
    def rp_his_id(self) -> int:
        return self._rp_his_id

    @property
    def tool_call_id(self) -> str:
        """Tool call ID for tool-result messages (OpenAI API requirement)."""
        return self._tool_call_id

    @tool_call_id.setter
    def tool_call_id(self, value: str) -> None:
        self._tool_call_id = value

    @property
    def tool_calls(self) -> list[dict] | None:
        """Tool calls attached to an assistant message (OpenAI format)."""
        return self._tool_calls

    @tool_calls.setter
    def tool_calls(self, value: list[dict] | None) -> None:
        self._tool_calls = value

    def is_user(self) -> bool:
        """Whether this message is from the user."""
        return self._role is Role.USER

    def is_system(self) -> bool:
        """Whether this message is a system message."""
        return self._role is Role.SYSTEM

    def is_assistant(self) -> bool:
        """Whether this message is from the assistant."""
        return self._role is Role.ASSISTANT

    def is_tool(self) -> bool:
        """Whether this message is a tool result."""
        return self._role is Role.TOOL

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {MsgKey.ROLE: self._role.value, MsgKey.CONTENT: self._content}
        if self._rp_his_id:
            d[MsgKey.RP_HIS_ID] = self._rp_his_id
        if self._tool_call_id:
            d["tool_call_id"] = self._tool_call_id
        if self._tool_calls:
            d["tool_calls"] = self._tool_calls
        return d


    @classmethod
    def from_dict(cls, d: dict[str, object]) -> Message:
        return cls(
            role=d[MsgKey.ROLE],
            content=d.get(MsgKey.CONTENT, ""),
            rp_his_id=d.get(MsgKey.RP_HIS_ID, 0),
            tool_call_id=d.get("tool_call_id", ""),
            tool_calls=d.get("tool_calls"),
        )

    def __repr__(self) -> str:
        return f"Message(role={self._role.value!r}, content={self._content[:40]!r}...)"


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
    - ``to_message_objects()`` 返回 ``list[Message]``（内部流转用）
    - ``get_layer(type_str)`` 按类型检索

    Usage::

        ctx: RPGContext = builder.build(...)
        msgs = ctx.to_message_objects()   # → list[Message]
        for m in msgs:
            ...  # 按 Message API 访问
    """

    # ── Layers ─────────────────────────────────────────────────────────

    fixed_layer: str = ""
    """[0] Fixed Layer — rendered prompt + lore + characters."""

    persistent_memory: str | None = None
    """[1] Persistent Memory — offline long-term memory content."""

    summary: str | None = None
    """[2] Summary Layer — compressed summaries (None if no summaries)."""

    hot_history: list[Message] = field(default_factory=list)
    """[3..N] Hot History — recent user/assistant Message objects."""

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

    def to_message_objects(self) -> list[Message]:
        """Flatten to a list of ``Message`` objects (no dict conversion).

        Use this when the caller wants to keep ``Message`` objects flowing
        through internal layers and only convert to dicts at the LLM
        provider boundary.
        """
        msgs: list[Message] = []

        if self.fixed_layer:
            msgs.append(Message(role=Role.SYSTEM, content=self.fixed_layer))
        if self.persistent_memory:
            msgs.append(Message(role=Role.SYSTEM, content=self.persistent_memory))
        if self.summary:
            msgs.append(Message(role=Role.SYSTEM, content=self.summary))

        for h in self.hot_history:
            msgs.append(h)

        if self.story_memory:
            msgs.append(Message(role=Role.SYSTEM, content=self.story_memory))
        if self.recalled_memory:
            msgs.append(Message(role=Role.SYSTEM, content=self.recalled_memory))
        if self.status_tables:
            msgs.append(Message(role=Role.SYSTEM, content=self.status_tables))

        parts: list[str] = []
        if self.user_before:
            parts.append(f"[user_prefix]{self.user_before}[/user_prefix]")
        if self.user_input:
            parts.append(self.user_input)
        if self.user_after:
            parts.append(f"[user_suffix]{self.user_after}[/user_suffix]")
        user_content = "\n\n".join(parts)
        if user_content:
            msgs.append(Message(role=Role.USER, content=user_content))

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
        _add(LayerType.FIXED, Role.SYSTEM, self.fixed_layer,
             _build_fixed_desc(lore_count, char_count))

        # [1] Persistent Memory
        _add(LayerType.PERSISTENT_MEMORY, Role.SYSTEM, self.persistent_memory,
             _preview_text(self.persistent_memory or "", 50))

        # [2] Summary
        _add(LayerType.SUMMARY, Role.SYSTEM, self.summary,
             _preview_text(self.summary or "", 50))

        # [3..N] Hot History
        if self.hot_history:
            tokens = token_counter.count_messages(self.hot_history)
            user_rounds = sum(1 for m in self.hot_history if m.is_user())
            layers.append(LayerInfo(
                type=LayerType.HOT_HISTORY, role="mixed",
                status="active",
                char_count=sum(len(m.content) for m in self.hot_history),
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
        _add(LayerType.STORY_MEMORY, Role.SYSTEM, self.story_memory,
             _build_story_memory_desc(self.story_memory))

        # [N+3] Recalled Memory
        _add(LayerType.RECALLED_MEMORY, Role.SYSTEM, self.recalled_memory,
             _preview_text(self.recalled_memory or "", 50))

        # [N+4] Status Tables
        _add(LayerType.STATUS_TABLES, Role.SYSTEM, self.status_tables,
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
                type=LayerType.USER_MESSAGE, role=Role.USER.value,
                status="active",
                char_count=len(user_content),
                token_count=token_counter.count(user_content),
                description=_preview_text(user_content, 50),
            ))
        else:
            layers.append(LayerInfo(
                type=LayerType.USER_MESSAGE, role=Role.USER.value,
                status="inactive", char_count=0, token_count=0,
                description="-",
            ))

        return layers

    def to_markdown(self, token_counter: TokenCounter) -> str:
        """Render context structure as a chat-friendly Markdown summary."""
        layers = self.layer_summary(token_counter)
        total_tokens = sum(l.token_count for l in layers)
        active_layers = sum(1 for l in layers if l.status == "active")

        lines = [
            "## 上下文概览",
            f"- 总 token: **{total_tokens:,}**",
            f"- 活跃层: **{active_layers} / {len(layers)}**",
        ]

        hot_rounds = getattr(self, "_hot_history_rounds", None)
        if hot_rounds is not None:
            lines.append(f"- 历史窗口: **{hot_rounds}** 轮")

        lines.append("")
        lines.append("## 分层明细")
        for index, info in enumerate(layers):
            tokens_str = f"{info.token_count:,}" if info.token_count > 0 else "-"
            lines.append(
                f"- [{index}] **{_layer_display_name(info.type)}**"
                f" ({info.role}, {info.status}, {tokens_str} tokens)"
            )
            if info.description and info.description != "-":
                lines.append(f"  - {info.description}")

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
        msgs: list[dict[str, object]],
        role: str,
        content: str | None,
        type_: str,
    ) -> None:
        if content:
            d = Message(role=role, content=content).to_dict()
            d["type"] = type_
            msgs.append(d)


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


def _preview_text(text: str, max_chars: int = 50) -> str:
    """Collapse multiline text into a compact single-line preview."""
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + "..."


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
    return _preview_text(content, 50)


def _build_status_desc(content: str | None) -> str:
    """Estimate status table count from rendered content."""
    if not content:
        return "-"
    count = content.count("\n### ")  # each table has a ### header
    extra = 1 if content.startswith("### ") else 0
    total = count + extra
    return f"{total} 张状态表" if total > 0 else _preview_text(content, 50)
