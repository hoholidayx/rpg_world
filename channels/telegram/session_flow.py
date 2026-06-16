"""Telegram 专用会话交互状态机。

负责 Telegram 渠道里的会话菜单、会话切换和二段式会话创建，
避免这些交互逻辑污染通用 adapter / core 命令分发。
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from rpg_world.rpg_core.agent.agent import RPGGameAgent

from rpg_world.rpg_core.session import SessionManager

_SESSION_PICKER_TOKEN_PREFIX = "tg_sess"
_SESSION_CREATE_TTL_SECONDS = 300
_MAX_SESSION_PICKER_ROWS = 20


@dataclass
class _PendingSessionCreate:
    started_at: float


@dataclass
class _PickerAction:
    kind: str
    session_id: str | None = None


class TelegramSessionFlow:
    """管理 Telegram 会话菜单、会话切换与 session_create 二段输入。"""

    def __init__(self) -> None:
        self._session_overrides: dict[str, str] = {}
        self._pending_session_create: dict[str, _PendingSessionCreate] = {}
        self._picker_actions: dict[str, _PickerAction] = {}

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

    def _new_picker_token(self) -> str:
        token = secrets.token_urlsafe(8)
        self._picker_actions[token] = _PickerAction(kind="noop")
        return token

    def _register_picker_action(self, action: _PickerAction) -> str:
        token = self._new_picker_token()
        self._picker_actions[token] = action
        return token

    def build_session_picker(self, sessions: list[str], current: str) -> InlineKeyboardMarkup:
        """构造可点击的会话选择菜单。"""
        rows: list[list[InlineKeyboardButton]] = []
        visible_sessions = sessions[:_MAX_SESSION_PICKER_ROWS]
        for sid in visible_sessions:
            label = f"{sid} （当前）" if sid == current else sid
            token = self._register_picker_action(_PickerAction(kind="switch", session_id=sid))
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"{_SESSION_PICKER_TOKEN_PREFIX}:{token}")]
            )

        create_token = self._register_picker_action(_PickerAction(kind="create"))
        rows.append([
            InlineKeyboardButton(text="新建会话", callback_data=f"{_SESSION_PICKER_TOKEN_PREFIX}:{create_token}"),
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
        agent: RPGGameAgent | None,
        send_text: Callable[[str], Awaitable[None]],
        auto_pin_created_session: bool = False,
    ) -> bool:
        """消费 session_create 的二段输入。"""
        if self.expire_session_create_flow(chat_id):
            await send_text("会话创建已超时，请重新发送 /session_create。")
            return True
        if not self._is_session_create_flow_active(chat_id):
            return False

        candidate = text.strip()
        if candidate.lower() == "/cancel":
            self.cancel_session_create_flow(chat_id)
            await send_text("已取消创建会话。")
            return True

        try:
            SessionManager.validate_session_id(candidate)
        except ValueError as exc:
            await send_text(f"[错误] 会话名无效：{exc}")
            return True

        if not agent:
            await send_text("会话创建暂不可用。")
            return True

        result = await agent.execute_command(f"/session_create {candidate}")
        if result.reply.startswith("[会话已创建: "):
            self.cancel_session_create_flow(chat_id)
            self.maybe_pin_created_session(
                chat_id,
                candidate,
                auto_pin=auto_pin_created_session,
            )
        await send_text(result.reply or "会话创建完成。")
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

        if name == "/session_create" and len(parts) == 1:
            self.start_session_create_flow(chat_id)
            await send_text(
                "请输入新会话 ID（仅字母、数字、下划线，长度不超过 64）。\n"
                "发送 /cancel 可取消创建。",
            )
            return True

        return False

    async def handle_callback_query(
        self,
        chat_id: str,
        callback_data: str,
        *,
        send_text: Callable[[str], Awaitable[None]],
        switch_session: Callable[[str], Awaitable[None]],
    ) -> bool:
        """处理会话菜单按钮点击。"""
        token = str(callback_data or "")
        if not token.startswith(f"{_SESSION_PICKER_TOKEN_PREFIX}:"):
            return False

        raw_token = token.split(":", maxsplit=1)[1]
        action = self._picker_actions.pop(raw_token, None)
        if action is None:
            await send_text("该会话菜单已失效，请重新输入 /sessions。")
            return True

        if action.kind == "create":
            self.start_session_create_flow(chat_id)
            await send_text(
                "请输入新会话 ID（仅字母、数字、下划线，长度不超过 64）。\n"
                "发送 /cancel 可取消创建。",
            )
            return True

        if action.kind == "switch" and action.session_id:
            await switch_session(action.session_id)
            self.pin_session(chat_id, action.session_id)
            await send_text(f"[已切换到会话: {action.session_id}]")
            return True

        return False
