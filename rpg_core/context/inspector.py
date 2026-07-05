"""Inspection helpers for structured RPG contexts.

This module is intentionally outside ``rpg_context.py`` so debug/UI output does
not add maintenance cost to the LLM context data model.
"""

from __future__ import annotations

from dataclasses import dataclass

from rpg_core.context.rpg_context import LayerType, Message, RPGContext, Role
from rpg_core.session.turns import count_roles
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
    ) -> None:
        self._ctx = ctx
        self._token_counter = token_counter
        self._hot_history_rounds = hot_history_rounds

    def layer_summary(self) -> list[LayerInfo]:
        return [
            LayerInfo(
                type=str(layer["type"]),
                role=str(layer["role"]),
                status=str(layer["status"]),
                char_count=int(layer["charCount"]),
                token_count=int(layer["tokenCount"]),
                description=str(layer["description"]),
            )
            for layer in self._layer_payloads()
        ]

    def to_payload(self, session_id: str = "") -> dict[str, object]:
        layers = self._layer_payloads()
        messages = [message.to_dict() for message in self._ctx.to_message_objects()]
        return {
            "formatVersion": "context-preview.v1",
            "sessionId": session_id,
            "hotHistoryRounds": self._hot_history_rounds,
            "totals": {
                "layerCount": len(layers),
                "activeLayers": sum(1 for layer in layers if layer["status"] == "active"),
                "tokenCount": sum(int(layer["tokenCount"]) for layer in layers),
                "messageCount": len(messages),
            },
            "layers": layers,
            "messages": messages,
        }

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
            LayerType.RECALLED_MEMORY,
            Role.SYSTEM.value,
            f"{len(self._ctx.recalled_memory.items)} 条召回记忆" if self._ctx.recalled_memory.active else "-",
        )
        self._add_rendered_layer_payload(
            layers,
            LayerType.STATUS_TABLES,
            Role.SYSTEM.value,
            f"{len(self._ctx.status_tables.tables)} 张状态表" if self._ctx.status_tables.active else "-",
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
        total_tokens = sum(l.token_count for l in layers)
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
                "tokenCount": self._token_counter.count(content),
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
            "tokenCount": self._token_counter.count_messages(self._ctx.hot_history.messages),
            "description": (
                f"{turn_count} 轮 / {len(self._ctx.hot_history.messages)} 条 "
                f"(user={_role_count(role_counts, Role.USER)}, assistant={_role_count(role_counts, Role.ASSISTANT)}, "
                f"tool={_role_count(role_counts, Role.TOOL)}, system={_role_count(role_counts, Role.SYSTEM)})"
            ),
            "content": _render_hot_history_content(self._ctx.hot_history.messages),
        })


def _role_count(role_counts: dict[str, int], role: Role) -> int:
    return role_counts[role.value]


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
