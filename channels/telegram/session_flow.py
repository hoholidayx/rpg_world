"""Telegram 专用会话交互状态机。

负责 Telegram 渠道里的会话菜单、会话切换和二段式临时交互，
避免这些交互逻辑污染通用 adapter / core 命令分发。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from channels.telegram.action_registry import (
    TelegramActionRegistry,
    TelegramCallbackAction,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_service.schemas import AgentSessionSummaryPayload

_SESSION_CREATE_TTL_SECONDS = 300
_MAX_SESSION_PICKER_ROWS = 20
SESSION_ACTION_SWITCH = "session_switch"
SESSION_ACTION_CREATE = "session_create"


def short_session_id(session_id: str) -> str:
    value = str(session_id)
    return value if len(value) <= 12 else value[-8:]


@dataclass
class _PendingSessionCreate:
    started_at: float


class TelegramSessionFlow:
    """管理 Telegram 会话菜单、会话切换与可复用二段输入状态。"""

    def __init__(self, action_registry: TelegramActionRegistry | None = None) -> None:
        self._session_overrides: dict[str, str] = {}
        self._pending_session_create: dict[str, _PendingSessionCreate] = {}
        self._action_registry = (
            action_registry if action_registry is not None else TelegramActionRegistry()
        )

    def get_session_id(self, chat_id: str, default_session_id: str) -> str:
        """优先返回当前 chat 被显式钉住的会话，否则返回默认值。"""
        pinned = self._session_overrides.get(chat_id)
        if pinned:
            return pinned
        return default_session_id

    def pin_session(self, chat_id: str, session_id: str) -> None:
        """把当前 chat 固定到指定会话。"""
        self._session_overrides[chat_id] = session_id

    def clear_pinned_session(self, chat_id: str) -> None:
        """清除当前 chat 的显式会话绑定。"""
        self._session_overrides.pop(chat_id, None)

    def build_session_picker(
        self,
        chat_id: str,
        sessions: list[AgentSessionSummaryPayload],
        current: str,
    ) -> InlineKeyboardMarkup:
        """构造可点击的会话选择菜单。"""
        rows: list[list[InlineKeyboardButton]] = []
        visible_sessions = sessions[:_MAX_SESSION_PICKER_ROWS]
        for session in visible_sessions:
            sid = str(session["session_id"])
            title = str(session.get("title") or "未命名会话")
            label = f"{'✓ ' if sid == current else ''}{title[:40]} · {short_session_id(sid)}"
            callback_data = self._action_registry.add(
                kind=SESSION_ACTION_SWITCH,
                chat_id=chat_id,
                session_id=current,
                payload={"target_session_id": sid},
            )
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=callback_data)]
            )

        create_callback_data = self._action_registry.add(
            kind=SESSION_ACTION_CREATE,
            chat_id=chat_id,
            session_id=current,
        )
        rows.append([
            InlineKeyboardButton(text="新建并进入", callback_data=create_callback_data),
        ])
        return InlineKeyboardMarkup(rows)

    def render_session_picker_text(
        self,
        sessions: list[AgentSessionSummaryPayload],
        current: str,
    ) -> str:
        """渲染会话列表文案。"""
        if not sessions:
            return "\n".join(
                [
                    "会话列表 (0):",
                    f"当前会话: {current}",
                    "点击下方“新建并进入”开始创建。",
                ]
            )

        lines = [
            f"会话列表 ({len(sessions)}):",
            f"当前会话: {current}",
            "点击下方按钮切换会话，或点“新建并进入”创建新的会话。",
        ]
        visible_sessions = sessions[:_MAX_SESSION_PICKER_ROWS]
        for session in visible_sessions:
            sid = str(session["session_id"])
            title = str(session.get("title") or "未命名会话")
            marker = " （当前）" if sid == current else ""
            lines.append(f"- {title} · {short_session_id(sid)}{marker}")
        if len(sessions) > len(visible_sessions):
            lines.append(f"... 还有 {len(sessions) - len(visible_sessions)} 个会话未展示，请使用命令直接切换。")
        return "\n".join(lines)

    def start_session_create_flow(self, chat_id: str) -> None:
        self._pending_session_create[chat_id] = _PendingSessionCreate(started_at=time.monotonic())

    def cancel_session_create_flow(self, chat_id: str) -> bool:
        """取消 Telegram 专属的二段创建状态。"""
        return self._pending_session_create.pop(chat_id, None) is not None

    def _is_session_create_flow_active(self, chat_id: str) -> bool:
        pending = self._pending_session_create.get(chat_id)
        if pending is None:
            return False
        if time.monotonic() - pending.started_at > _SESSION_CREATE_TTL_SECONDS:
            self._pending_session_create.pop(chat_id, None)
            return False
        return True

    def expire_session_create_flow(self, chat_id: str) -> bool:
        """若二段创建已超时则清理并返回 True。"""
        pending = self._pending_session_create.get(chat_id)
        if pending is None:
            return False
        if time.monotonic() - pending.started_at <= _SESSION_CREATE_TTL_SECONDS:
            return False
        self._pending_session_create.pop(chat_id, None)
        return True

    async def handle_plain_text(
        self,
        chat_id: str,
        text: str,
        *,
        send_text: Callable[[str], Awaitable[None]],
        create_and_switch: Callable[[str], Awaitable[str]],
    ) -> bool:
        """消费“输入标题后新建并进入”的二段创建状态。"""
        if self.expire_session_create_flow(chat_id):
            await send_text("会话创建已超时，请重新发送 /session_create。")
            return True
        if not self._is_session_create_flow_active(chat_id):
            return False

        title = text.strip()
        if title.lower() == "/cancel":
            self.cancel_session_create_flow(chat_id)
            await send_text("已取消创建会话。")
            return True

        if not title:
            await send_text("会话标题不能为空，请重新输入，或发送 /cancel 取消。")
            return True
        active_session_id = await create_and_switch(title)
        self.cancel_session_create_flow(chat_id)
        await send_text(f"已新建并进入会话：{title} · {short_session_id(active_session_id)}")
        return True

    async def handle_command(
        self,
        chat_id: str,
        command: str,
        *,
        send_text: Callable[[str], Awaitable[None]],
        send_session_picker: Callable[[], Awaitable[None]],
    ) -> bool:
        """处理 Telegram 专属临时命令。"""
        parts = command.split()
        name = parts[0].lower()

        if name == "/cancel":
            if self.cancel_session_create_flow(chat_id):
                await send_text("已取消创建会话。")
            else:
                await send_text("当前没有进行中的会话创建。")
            return True

        if name == "/sessions":
            await send_session_picker()
            return True

        if name == "/session_switch" and len(parts) == 1:
            await send_session_picker()
            return True

        return False

    async def handle_action(
        self,
        action: TelegramCallbackAction,
        *,
        send_text: Callable[[str], Awaitable[None]],
        switch_session: Callable[[str], Awaitable[str]],
        create_session: Callable[[], Awaitable[None]],
    ) -> bool:
        """执行已由统一 registry 校验并 claim 的会话 action。"""
        if action.kind == SESSION_ACTION_CREATE:
            await create_session()
            return True

        if action.kind == SESSION_ACTION_SWITCH:
            target_session_id = str(action.payload.get("target_session_id") or "")
            if not target_session_id:
                return False
            active_session_id = await switch_session(target_session_id)
            await send_text(f"[已切换到会话: {active_session_id}]")
            return True

        return False
