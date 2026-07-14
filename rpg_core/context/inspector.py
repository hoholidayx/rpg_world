"""Inspection helpers for structured RPG contexts.

This module is intentionally outside ``rpg_context.py`` so debug/UI output does
not add maintenance cost to the LLM context data model.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from rpg_core.context.usage import estimate_rendered_context_usage
from rpg_core.context.rpg_context import LayerType, Message, RPGContext, Role
from rpg_core.session.turns import count_roles, count_turns
from rpg_core.utils.tokenizer import TokenCounter


@dataclass
class LayerInfo:
    """Structured metadata for a single context layer."""

    type: str
    role: str
    status: str
    char_count: int
    token_count: int
    description: str


class ContextInspector:
    """Build human-facing diagnostics for an ``RPGContext``."""

    def __init__(
        self,
        ctx: RPGContext,
        token_counter: TokenCounter,
        hot_history_rounds: int | None = None,
        context_limit: int | None = None,
    ) -> None:
        self._ctx = ctx
        self._token_counter = token_counter
        self._hot_history_rounds = hot_history_rounds
        self._context_limit = context_limit
        self._estimation_error: str | None = None

    def layer_summary(self) -> list[LayerInfo]:
        return [
            LayerInfo(
                type=str(layer.get("type", "")),
                role=str(layer.get("role", "")),
                status=str(layer.get("status", "")),
                char_count=_int_value(layer.get("charCount")),
                token_count=_int_value(layer.get("tokenCount")),
                description=str(layer.get("description", "")),
            )
            for layer in self._layer_payloads()
        ]

    def to_payload(self, session_id: str = "") -> dict[str, object]:
        layers = self._layer_payloads()
        message_objects = self._ctx.to_message_objects()
        messages = [message.to_dict() for message in message_objects]
        usage_estimate = estimate_rendered_context_usage(
            message_objects,
            self._token_counter,
            context_limit=self._context_limit,
        )
        token_count = int(usage_estimate.used_tokens or 0)
        if usage_estimate.error_reason:
            self._estimation_error = usage_estimate.error_reason
        payload: dict[str, object] = {
            "formatVersion": "context-preview.v1",
            "sessionId": session_id,
            "hotHistoryRounds": self._hot_history_rounds,
            "totals": {
                "layerCount": len(layers),
                "activeLayers": sum(1 for layer in layers if layer.get("status") == "active"),
                "tokenCount": token_count,
                "messageCount": len(messages),
            },
            "layers": layers,
            "messages": messages,
        }
        payload["usageEstimate"] = usage_estimate.to_camel_payload()
        if self._estimation_error:
            logger.warning(
                "[ContextInspector] usage estimate fallback: session_id={}, used_tokens={}, context_limit={}, error={}",
                session_id or "-",
                token_count,
                self._context_limit,
                self._estimation_error,
            )
        else:
            logger.debug(
                "[ContextInspector] usage estimate built: session_id={}, used_tokens={}, context_limit={}, layers={}, messages={}",
                session_id or "-",
                token_count,
                self._context_limit,
                len(layers),
                len(messages),
            )
        return payload

    def _layer_payloads(self) -> list[dict[str, object]]:
        layers: list[dict[str, object]] = []
        self._add_rendered_layer_payload(
            layers,
            LayerType.FIXED,
            Role.SYSTEM.value,
            _build_fixed_desc(
                section_count=len(self._ctx.fixed_layer.sections),
                lore_count=len(self._ctx.fixed_layer.lorebook_entries),
                char_count=len(self._ctx.fixed_layer.characters),
            ),
        )
        self._add_rendered_layer_payload(
            layers,
            LayerType.PERSISTENT_MEMORY,
            Role.SYSTEM.value,
            f"{len(self._ctx.persistent_memory.sections)} 段常驻记忆"
            if self._ctx.persistent_memory.active
            else "-",
        )
        self._add_rendered_layer_payload(
            layers,
            LayerType.SUMMARY,
            Role.SYSTEM.value,
            _preview_text(self._ctx.summary.text or "", 50),
        )
        self._add_hot_history_payload(layers)
        self._add_rendered_layer_payload(
            layers,
            LayerType.STORY_MEMORY,
            Role.SYSTEM.value,
            f"{len(self._ctx.story_memory.details)} 条剧情细节" if self._ctx.story_memory.active else "-",
        )
        self._add_rendered_layer_payload(
            layers,
            LayerType.STATUS_TABLES,
            Role.SYSTEM.value,
            f"{len(self._ctx.status_tables.tables)} 张状态表" if self._ctx.status_tables.active else "-",
        )
        self._add_rendered_layer_payload(
            layers,
            LayerType.RECALLED_MEMORY,
            Role.SYSTEM.value,
            f"{len(self._ctx.recalled_memory.items)} 条召回记忆" if self._ctx.recalled_memory.active else "-",
        )
        self._add_rendered_layer_payload(
            layers,
            LayerType.RP_MODULES,
            Role.SYSTEM.value,
            f"{len(self._ctx.rp_modules.sections)} 个 RP 模块运行态" if self._ctx.rp_modules.active else "-",
        )
        # USER_MESSAGE 的摘要需要包含 scene/user prefix 等最终拼接结果，所以这里先渲染再预览。
        user_content = self._ctx.render_layer(LayerType.USER_MESSAGE)
        self._add_layer_payload(
            layers,
            LayerType.USER_MESSAGE,
            Role.USER.value,
            user_content,
            _preview_text(user_content or "", 50),
        )
        return layers

    def to_markdown(self) -> str:
        layers = self.layer_summary()
        total_tokens = self._count_messages(self._ctx.to_message_objects())
        active_layers = sum(1 for l in layers if l.status == "active")

        lines = [
            "## 上下文概览",
            f"- 总 token: **{total_tokens:,}**",
            f"- 活跃层: **{active_layers} / {len(layers)}**",
        ]

        if self._ctx.hot_history.messages:
            from rpg_core.session.manager import SessionManager

            role_counts = count_roles(self._ctx.hot_history.messages)
            lines.append(f"- 历史消息: **{len(self._ctx.hot_history.messages)}** 条")
            lines.append(f"- 历史轮数: **{SessionManager.count_turns(self._ctx.hot_history.messages)}** 轮")
            lines.append(
                "- 角色分布: "
                f"user {_role_count(role_counts, Role.USER)}, assistant {_role_count(role_counts, Role.ASSISTANT)}, "
                f"tool {_role_count(role_counts, Role.TOOL)}, system {_role_count(role_counts, Role.SYSTEM)}"
            )

        if self._hot_history_rounds is not None:
            lines.append(f"- 历史窗口: **{self._hot_history_rounds}** 轮")

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

    def to_verbose_log(self) -> str:
        """Render a complete, layered context view for verbose logs.

        Hot history deliberately exposes only its logical turn count: logging
        the full conversation here would duplicate potentially large session
        history while making the other runtime layers difficult to inspect.
        """
        layers = (
            (LayerType.FIXED, Role.SYSTEM.value),
            (LayerType.PERSISTENT_MEMORY, Role.SYSTEM.value),
            (LayerType.SUMMARY, Role.SYSTEM.value),
            (LayerType.HOT_HISTORY, "mixed"),
            (LayerType.STORY_MEMORY, Role.SYSTEM.value),
            (LayerType.STATUS_TABLES, Role.SYSTEM.value),
            (LayerType.RECALLED_MEMORY, Role.SYSTEM.value),
            (LayerType.RP_MODULES, Role.SYSTEM.value),
            (LayerType.USER_MESSAGE, Role.USER.value),
        )
        lines = ["当前 Context（结构化分层）："]
        for index, (type_, role) in enumerate(layers):
            is_last = index == len(layers) - 1
            branch = "└──" if is_last else "├──"
            child_prefix = "    " if is_last else "│   "
            lines.append(f"{branch} {type_} ({role})")

            if type_ == LayerType.HOT_HISTORY:
                lines.append(
                    f"{child_prefix}└── turns={count_turns(self._ctx.hot_history.messages)}"
                )
                continue

            content = self._ctx.render_layer(type_)
            if not content:
                lines.append(f"{child_prefix}└── <empty>")
                continue

            lines.append(f"{child_prefix}└── content:")
            content_prefix = f"{child_prefix}    "
            lines.extend(f"{content_prefix}{line}" for line in content.splitlines())

        return "\n".join(lines)

    def _add_rendered_layer_payload(
        self,
        layers: list[dict[str, object]],
        type_: str,
        role: str,
        description: str,
    ) -> None:
        self._add_layer_payload(layers, type_, role, self._ctx.render_layer(type_), description)

    def _add_layer_payload(
        self,
        layers: list[dict[str, object]],
        type_: str,
        role: str,
        content: str | None,
        description: str,
    ) -> None:
        if content:
            layers.append({
                "index": len(layers),
                "type": type_,
                "role": role,
                "status": "active",
                "charCount": len(content),
                "tokenCount": self._count_text(content),
                "description": description,
                "content": content,
            })
            return
        layers.append({
            "index": len(layers),
            "type": type_,
            "role": role,
            "status": "inactive",
            "charCount": 0,
            "tokenCount": 0,
            "description": "-",
            "content": "",
        })

    def _add_hot_history_payload(self, layers: list[dict[str, object]]) -> None:
        if not self._ctx.hot_history.messages:
            layers.append({
                "index": len(layers),
                "type": LayerType.HOT_HISTORY,
                "role": "mixed",
                "status": "inactive",
                "charCount": 0,
                "tokenCount": 0,
                "description": "-",
                "content": "",
            })
            return

        from rpg_core.session.manager import SessionManager

        role_counts = count_roles(self._ctx.hot_history.messages)
        turn_count = SessionManager.count_turns(self._ctx.hot_history.messages)
        layers.append({
            "index": len(layers),
            "type": LayerType.HOT_HISTORY,
            "role": "mixed",
            "status": "active",
            "charCount": sum(len(m.content) for m in self._ctx.hot_history.messages),
            "tokenCount": self._count_messages(self._ctx.hot_history.messages),
            "description": (
                f"{turn_count} 轮 / {len(self._ctx.hot_history.messages)} 条 "
                f"(user={_role_count(role_counts, Role.USER)}, assistant={_role_count(role_counts, Role.ASSISTANT)}, "
                f"tool={_role_count(role_counts, Role.TOOL)}, system={_role_count(role_counts, Role.SYSTEM)})"
            ),
            "content": _render_hot_history_content(self._ctx.hot_history.messages),
        })

    def _count_text(self, content: str) -> int:
        try:
            return self._token_counter.count(content)
        except Exception as exc:
            self._estimation_error = str(exc) or exc.__class__.__name__
            return max(0, len(content) // 4)

    def _count_messages(self, messages: list[Message]) -> int:
        try:
            return self._token_counter.count_messages(messages)
        except Exception as exc:
            self._estimation_error = str(exc) or exc.__class__.__name__
            return sum(max(0, len(message.content) // 4) for message in messages)


def _role_count(role_counts: dict[str, int], role: Role) -> int:
    return role_counts[role.value]


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _layer_display_name(type_: str) -> str:
    names = {
        LayerType.FIXED: "Fixed Layer",
        LayerType.PERSISTENT_MEMORY: "Persistent Memory",
        LayerType.SUMMARY: "Summary",
        LayerType.HOT_HISTORY: "Hot History",
        LayerType.STORY_MEMORY: "Story Memory",
        LayerType.RECALLED_MEMORY: "Recalled Memory",
        LayerType.STATUS_TABLES: "Status Tables",
        LayerType.RP_MODULES: "RP Modules",
        LayerType.USER_MESSAGE: "User Message",
    }
    return names.get(type_, type_)


def _preview_text(text: str, max_chars: int = 50) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + "..."


def _render_hot_history_content(messages: list[Message]) -> str:
    return "\n\n".join(f"[{message.role.value}]\n{message.content}" for message in messages)


def _build_fixed_desc(section_count: int, lore_count: int, char_count: int) -> str:
    parts = [f"{section_count} 段固定指令"] if section_count else []
    if lore_count:
        parts.append(f"{lore_count} 条世界书")
    if char_count:
        parts.append(f"{char_count} 张角色卡")
    return " + ".join(parts) if parts else "-"
