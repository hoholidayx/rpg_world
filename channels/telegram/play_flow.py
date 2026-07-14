"""Telegram lightweight play entry and player-role keyboards."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from channels.telegram.action_registry import TelegramActionRegistry
from channels.telegram.session_flow import short_session_id

if TYPE_CHECKING:
    from agent_service.schemas import AgentSessionOverviewPayload

PLAY_ACTION_CHOOSE_ROLE = "play_choose_role"
PLAY_ACTION_OPEN_SESSIONS = "play_open_sessions"
PLAY_ACTION_START = "play_start"
PLAY_ACTION_BIND_ROLE = "play_bind_role"


class TelegramPlayFlow:
    """Build the minimal playable entry card and role picker."""

    def __init__(self, action_registry: TelegramActionRegistry) -> None:
        self._action_registry = action_registry

    @staticmethod
    def render_entry_text(overview: AgentSessionOverviewPayload) -> str:
        story_title = str(overview.get("story_title") or f"故事 {overview['story_id']}")
        session_title = str(overview.get("session_title") or "未命名会话")
        session_id = str(overview["session_id"])
        player = overview.get("player_character")
        player_name = str(player.get("name") or "尚未选择") if player else "尚未选择"
        return "\n".join(
            [
                "RPG World",
                f"当前故事：{story_title}",
                f"当前会话：{session_title} · {short_session_id(session_id)}",
                f"玩家角色：{player_name}",
            ]
        )

    def build_entry_keyboard(
        self,
        chat_id: str,
        overview: AgentSessionOverviewPayload,
    ) -> InlineKeyboardMarkup:
        session_id = str(overview["session_id"])
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "选择角色",
                        callback_data=self._action_registry.add(
                            kind=PLAY_ACTION_CHOOSE_ROLE,
                            chat_id=chat_id,
                            session_id=session_id,
                        ),
                    ),
                    InlineKeyboardButton(
                        "切换会话",
                        callback_data=self._action_registry.add(
                            kind=PLAY_ACTION_OPEN_SESSIONS,
                            chat_id=chat_id,
                            session_id=session_id,
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "开始游玩",
                        callback_data=self._action_registry.add(
                            kind=PLAY_ACTION_START,
                            chat_id=chat_id,
                            session_id=session_id,
                        ),
                    )
                ],
            ]
        )

    @staticmethod
    def render_role_picker_text(overview: AgentSessionOverviewPayload) -> str:
        options = overview.get("role_options", [])
        if not options:
            return "当前故事还没有可扮演角色，请先在 Play WebUI 中配置。"
        current = overview.get("player_character")
        current_name = str(current.get("name") or "") if current else ""
        suffix = f"\n当前角色：{current_name}" if current_name else ""
        return f"请选择你要扮演的角色：{suffix}"

    def build_role_picker(
        self,
        chat_id: str,
        overview: AgentSessionOverviewPayload,
    ) -> InlineKeyboardMarkup | None:
        options = overview.get("role_options", [])
        if not options:
            return None
        session_id = str(overview["session_id"])
        current = overview.get("player_character")
        current_id = int(current["character_id"]) if current else None
        rows: list[list[InlineKeyboardButton]] = []
        for option in options:
            character_id = int(option["character_id"])
            name = str(option.get("name") or f"角色 {character_id}")
            marker = "✓ " if character_id == current_id else ""
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{marker}{name[:48]}",
                        callback_data=self._action_registry.add(
                            kind=PLAY_ACTION_BIND_ROLE,
                            chat_id=chat_id,
                            session_id=session_id,
                            payload={"character_id": character_id},
                        ),
                    )
                ]
            )
        return InlineKeyboardMarkup(rows)


__all__ = [
    "PLAY_ACTION_BIND_ROLE",
    "PLAY_ACTION_CHOOSE_ROLE",
    "PLAY_ACTION_OPEN_SESSIONS",
    "PLAY_ACTION_START",
    "TelegramPlayFlow",
]
