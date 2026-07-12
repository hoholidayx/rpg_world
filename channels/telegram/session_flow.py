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

    from agent_service.client import AgentClient

_SESSION_CREATE_TTL_SECONDS = 300
_MAX_SESSION_PICKER_ROWS = 20
SESSION_ACTION_SWITCH = "session_switch"
SESSION_ACTION_CREATE = "session_create"


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

    def maybe_pin_created_session(self, chat_id: str, session_id: str, *, auto_pin: bool = False) -> None:
        """按产品开关决定是否把新建会话立即固定到当前 chat。

        当前产品要求：新建会话后不立即 pin。这里保留一个集中入口，
        若后续需求改为“创建后自动切换”，只需打开调用方的
        ``auto_pin_created_session`` 配置并复用该方法。
        """
        if auto_pin:
            self.pin_session(chat_id, session_id)

    def clear_pinned_session(self, chat_id: str) -> None:
        """清除当前 chat 的显式会话绑定。"""
        self._session_overrides.pop(chat_id, None)

    def build_session_picker(
        self,
        chat_id: str,
        sessions: list[str],
        current: str,
    ) -> InlineKeyboardMarkup:
        """构造可点击的会话选择菜单。"""
        rows: list[list[InlineKeyboardButton]] = []
        visible_sessions = sessions[:_MAX_SESSION_PICKER_ROWS]
        for sid in visible_sessions:
            label = f"{sid} （当前）" if sid == current else sid
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
            InlineKeyboardButton(text="新建会话", callback_data=create_callback_data),
        ])
        return InlineKeyboardMarkup(rows)

    def render_session_picker_text(self, sessions: list[str], current: str) -> str:
        """渲染会话列表文案。"""
        if not sessions:
            return "\n".join(
                [
                    "会话列表 (0):",
                    f"当前会话: {current}",
                    "点击下方“新建会话”开始创建。",
                ]
            )

        lines = [
            f"会话列表 ({len(sessions)}):",
            f"当前会话: {current}",
            "点击下方按钮切换会话，或点“新建会话”创建新的会话。",
        ]
        visible_sessions = sessions[:_MAX_SESSION_PICKER_ROWS]
        for sid in visible_sessions:
            marker = " （当前）" if sid == current else ""
            lines.append(f"- {sid}{marker}")
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
        agent_client: AgentClient | None,
        workspace_id: str,
        story_id: int,
        send_text: Callable[[str], Awaitable[None]],
        auto_pin_created_session: bool = False,
    ) -> bool:
        """消费保留的二段创建状态。

        当前 /session_create 已不再进入该流程；该实现仅保留给后续
        Telegram 专属二段交互复用。
        """
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

        if agent_client is not None:
            result = await agent_client.create_session(
                workspace_id,
                story_id,
                title=title,
            )
            created_session_id = str(result.get("session_id") or "")
            reply = f"[会话已创建: {created_session_id}]" if created_session_id else "会话创建完成。"
        else:
            await send_text("会话创建暂不可用。")
            return True
        if created_session_id:
            self.cancel_session_create_flow(chat_id)
            self.maybe_pin_created_session(
                chat_id,
                created_session_id,
                auto_pin=auto_pin_created_session,
            )
        await send_text(reply or "会话创建完成。")
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
