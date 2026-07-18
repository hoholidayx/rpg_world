"""TelegramAdapter — 基于 python-telegram-bot 的 Telegram 渠道适配器。

支持两种模式：
- **流式（streaming=True）**：通过 ``TelegramTurnFlow`` 逐段编辑消息实现实时输出
- **非流式（streaming=False）**：一次性通过 ``send_text`` 发送完整回复

用法::

    from channels import TelegramAdapter

    adapter = TelegramAdapter(token="env:TELEGRAM_BOT_TOKEN", streaming=True)
    adapter.bind_agent_client(client)
    await adapter.start()
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from loguru import logger
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, RetryAfter, TelegramError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from channels.base import ChannelAdapter
from channels.telegram.action_registry import TelegramActionRegistry
from channels.telegram.play_flow import (
    PLAY_ACTION_BIND_ROLE,
    PLAY_ACTION_CHOOSE_ROLE,
    PLAY_ACTION_OPEN_SESSIONS,
    PLAY_ACTION_START,
    TelegramPlayFlow,
)
from channels.telegram.render import (
    chunk_rendered_text,
    project_rp_text,
    render_markdown_to_telegram_html,
)
from channels.telegram.session_flow import TelegramSessionFlow, short_session_id
from channels.telegram.turn_flow import (
    ActiveTelegramTurn,
    TelegramTurnBusyReason,
    TelegramTurnFlow,
)
from rpg_core.agent.protocol import TurnCancelStatus

if TYPE_CHECKING:
    from agent_service.client import AgentClient
    from agent_service.schemas import AgentSessionOverviewPayload

_TELEGRAM_PARSE_MODE = "HTML"
_TELEGRAM_COMMAND_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_CALLBACK_INVALID_TEXT = "该菜单已失效，请重新打开。"
_CALLBACK_BUSY_TEXT = "当前会话正在生成，请完成后再操作。"
_CHAT_BUSY_TEXT = "当前消息仍在生成，请等待完成后再发送。"
_SESSION_BUSY_TEXT = "当前会话正在处理另一条消息，请稍后再试。"
_COMMAND_BUSY_TEXT = "当前会话正在生成，请完成后再执行命令。"
_GENERIC_FAILURE_TEXT = "处理消息失败，请稍后重试。"
_TURN_ACTION_STOP = "turn_stop"
_LOCAL_COMMANDS = {
    "start": "打开游玩入口",
    "help": "查看全部可用命令",
    "role_bind": "选择或切换玩家角色",
    "sessions": "查看并切换会话",
    "session_create": "新建并进入会话",
    "clear": "重置当前会话并重新开始游戏",
    "compact": "压缩当前会话上下文",
    "stop": "停止当前生成",
    "cancel": "取消正在输入的新会话标题",
}


def _preview_text(text: str, limit: int = 120) -> str:
    """返回适合日志输出的短文本预览。"""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _normalize_telegram_command(text: str) -> str:
    """把 Telegram command 文本规范化为 agent 可识别的格式。"""
    if not text.startswith("/"):
        return text
    parts = text.split(maxsplit=1)
    command = parts[0].split("@", maxsplit=1)[0].lower()
    if len(parts) == 1:
        return command
    return f"{command} {parts[1]}"


def _telegram_menu_command_name(command: str) -> str:
    """把后端命令名转换成 Telegram 菜单里允许的命令名。"""
    name = command.strip().split(maxsplit=1)[0].lstrip("/").split("@", maxsplit=1)[0].lower()
    if not _TELEGRAM_COMMAND_RE.fullmatch(name):
        return ""
    return name


def _telegram_command_description(description: str, limit: int = 256) -> str:
    """返回 Telegram 菜单允许的命令描述。"""
    clean = " ".join(str(description or "").split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1]}…"


class TelegramAdapter(ChannelAdapter):
    """Telegram 渠道适配器。

    基于 ``python-telegram-bot`` 的 ``Application`` 类实现长轮询。

    Parameters
    ----------
    token:
        Telegram Bot Token。
    streaming:
        ``True`` 启用流式输出（逐段编辑消息），
        ``False`` 为一次性发送完整回复。
    agent_client:
        Shared Agent service client.
    """

    def __init__(
        self,
        token: str,
        *,
        bot_name: str = "default",
        streaming: bool = True,
        proxy: str = "",
        stream_edit_interval_ms: int = 800,
        stream_edit_min_chars: int = 24,
        request_timeout_ms: int = 5000,
        agent_client: AgentClient | None = None,
        workspace: str | None = None,
        workspace_id: str | None = None,
        story_id: int | None = None,
        player_character_id: int = 0,
        session_id: str | None = None,
        session_title: str | None = None,
    ) -> None:
        super().__init__()
        self._bot_name = bot_name
        self._token = token
        self._streaming = streaming
        self._proxy = proxy
        self._stream_edit_interval = max(0, stream_edit_interval_ms) / 1000.0
        self._stream_edit_min_chars = max(1, stream_edit_min_chars)
        self._request_timeout = max(0, request_timeout_ms) / 1000.0
        self._workspace_override = (workspace or "").strip() or None
        self._workspace_id = (workspace_id or "").strip()
        self._story_id = int(story_id or 0)
        self._player_character_id = int(player_character_id or 0)
        self._default_session_id = (session_id or "").strip()
        self._session_title = (session_title or bot_name or "Telegram").strip()
        self._app: Application | None = None
        self._action_registry = TelegramActionRegistry()
        self._session_flow = TelegramSessionFlow(self._action_registry)
        self._play_flow = TelegramPlayFlow(self._action_registry)
        self._turn_flow = TelegramTurnFlow(
            presenter=self,
            streaming=self._streaming,
            stream_edit_interval_seconds=self._stream_edit_interval,
            stream_edit_min_chars=self._stream_edit_min_chars,
            stop_markup_factory=self._build_stop_markup,
            terminal_cleanup=self._cleanup_turn_action,
        )
        if agent_client:
            self.bind_agent_client(agent_client)

    @property
    def name(self) -> str:
        return f"telegram_{self._bot_name}"

    def get_workspace(self) -> str:
        if self._workspace_override:
            return self._workspace_override
        raise RuntimeError("Telegram workspace is not resolved")

    def bind_agent_client(self, client: AgentClient) -> None:
        super().bind_agent_client(client)
        self._turn_flow.bind_agent_client(client)

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 Telegram 长轮询。"""
        logger.info(
            "telegram: preparing adapter bot={} (streaming={}, proxy={}, interval_ms={}, min_chars={}, request_timeout_ms={})",
            self._bot_name,
            self._streaming,
            self._proxy or "<disabled>",
            int(self._stream_edit_interval * 1000),
            self._stream_edit_min_chars,
            int(self._request_timeout * 1000),
        )
        if not self._is_valid_token(self._token):
            raise ValueError("telegram: bot_token is empty")

        builder = Application.builder().token(self._token)
        if self._proxy:
            builder = builder.proxy(self._proxy).get_updates_proxy(self._proxy)
        self._app = builder.build()
        self._app.add_error_handler(self._on_error)
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self._on_message,
        ))
        self._app.add_handler(MessageHandler(filters.COMMAND, self._on_command))
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))
        logger.info("telegram: initializing application")
        await self._app.initialize()
        await self._configure_bot_commands()
        logger.info("telegram: starting application")
        await self._app.start()
        logger.info("telegram: starting long polling")
        await self._app.updater.start_polling()
        logger.info("telegram: long polling started")

    async def stop(self) -> None:
        """优雅关闭 Telegram 连接。"""
        if not self._app:
            await self._turn_flow.shutdown()
            self._action_registry.clear()
            return
        app = self._app
        logger.info("telegram: stopping adapter bot={}", self._bot_name)
        try:
            try:
                await app.updater.stop()
            except Exception:
                logger.exception("telegram: updater stop failed bot={}", self._bot_name)
            try:
                await self._turn_flow.shutdown()
            except Exception:
                logger.exception("telegram: turn flow shutdown failed bot={}", self._bot_name)
            self._action_registry.clear()
            try:
                await app.stop()
            except Exception:
                logger.exception("telegram: application stop failed bot={}", self._bot_name)
            try:
                await app.shutdown()
            except Exception:
                logger.exception("telegram: application shutdown failed bot={}", self._bot_name)
        finally:
            self._app = None
        logger.info("telegram: adapter stopped bot={}", self._bot_name)

    # ── 消息发送 ────────────────────────────────────────────────────────

    @staticmethod
    def _is_valid_token(token: str) -> bool:
        return bool(str(token).strip())

    async def _request_with_timeout(self, chat_id: str, action: str, awaitable):
        """对 Telegram 请求加超时，避免单次 API 调用长时间阻塞。"""
        try:
            if self._request_timeout <= 0:
                return await awaitable
            return await asyncio.wait_for(awaitable, timeout=self._request_timeout)
        except TimeoutError:
            logger.warning(
                "telegram: {} timed out bot={} chat_id={} timeout_ms={}",
                action,
                self._bot_name,
                chat_id,
                int(self._request_timeout * 1000),
            )
            return None
        except RetryAfter as exc:
            logger.warning(
                "telegram: {} rate limited bot={} chat_id={} retry_after={}s",
                action,
                self._bot_name,
                chat_id,
                exc.retry_after,
            )
            return None
        except BadRequest as exc:
            if "Message is not modified" in str(exc):
                logger.debug(
                    "telegram: {} ignored unchanged message bot={} chat_id={}",
                    action,
                    self._bot_name,
                    chat_id,
                )
                return None
            logger.warning("telegram: {} bad request bot={} chat_id={} error={}", action, self._bot_name, chat_id, exc)
            return None
        except (TimedOut, TelegramError, OSError) as exc:
            logger.warning("telegram: {} failed bot={} chat_id={} error={}", action, self._bot_name, chat_id, exc)
            return None
        except Exception:
            logger.exception("telegram: {} unexpected failure bot={} chat_id={}", action, self._bot_name, chat_id)
            return None

    def get_session_id(self, chat_id: str) -> str:
        """优先返回 Telegram chat 绑定的显式 session，否则使用默认映射。"""
        if not self._default_session_id:
            raise RuntimeError("Telegram default session is not resolved")
        return self._session_flow.get_session_id(chat_id, self._default_session_id)

    async def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        project_rp: bool = False,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """发送完整文本消息。超出 4096 字符自动分块。"""
        if not self._app:
            logger.warning("telegram: send_text skipped because application is not ready")
            return
        display_text = project_rp_text(text) if project_rp else text
        rendered = render_markdown_to_telegram_html(display_text)
        logger.debug(
            "telegram: sending text bot={} chat_id={} chunks={} preview={}",
            self._bot_name,
            chat_id,
            len(chunk_rendered_text(rendered)),
            _preview_text(text),
        )
        for index, chunk in enumerate(chunk_rendered_text(rendered)):
            await self.send_html(
                chat_id,
                chunk,
                reply_markup=reply_markup if index == 0 else None,
            )

    async def send_html(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> int | None:
        """Send one already-rendered Telegram HTML message."""
        if not self._app:
            logger.warning("telegram: send_html skipped because application is not ready")
            return None
        send_kwargs: dict[str, object] = {
            "chat_id": int(chat_id),
            "text": text,
            "parse_mode": _TELEGRAM_PARSE_MODE,
        }
        if reply_markup is not None:
            send_kwargs["reply_markup"] = reply_markup
        message = await self._request_with_timeout(
            chat_id,
            "send_message",
            self._app.bot.send_message(**send_kwargs),
        )
        message_id = getattr(message, "message_id", None)
        return int(message_id) if message_id is not None else None

    async def edit_html(self, chat_id: str, message_id: int, text: str) -> bool:
        """Edit one Telegram message with already-rendered HTML."""
        if not self._app:
            return False
        result = await self._request_with_timeout(
            chat_id,
            "edit_message_text",
            self._app.bot.edit_message_text(
                chat_id=int(chat_id),
                message_id=int(message_id),
                text=text,
                parse_mode=_TELEGRAM_PARSE_MODE,
            ),
        )
        return result is not None

    async def delete_message(self, chat_id: str, message_id: int) -> bool:
        """Best-effort deletion used when a final placeholder edit fails."""
        if not self._app:
            return False
        result = await self._request_with_timeout(
            chat_id,
            "delete_message",
            self._app.bot.delete_message(
                chat_id=int(chat_id),
                message_id=int(message_id),
            ),
        )
        return result is not None

    async def clear_reply_markup(self, chat_id: str, message_id: int) -> bool:
        """Remove terminal inline controls from a turn message."""
        if not self._app:
            return False
        result = await self._request_with_timeout(
            chat_id,
            "edit_message_reply_markup",
            self._app.bot.edit_message_reply_markup(
                chat_id=int(chat_id),
                message_id=int(message_id),
                reply_markup=None,
            ),
        )
        return result is not None

    def _build_stop_markup(self, active: ActiveTelegramTurn) -> InlineKeyboardMarkup | None:
        if not self._streaming:
            return None
        action = self._action_registry.create(
            kind=_TURN_ACTION_STOP,
            chat_id=active.chat_id,
            session_id=active.session_id,
        )
        callback_data = self._action_registry.register(action)
        active.stop_action_token = action.token
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("停止生成", callback_data=callback_data)]]
        )

    def _cleanup_turn_action(self, active: ActiveTelegramTurn) -> None:
        if active.stop_action_token:
            self._action_registry.invalidate(active.stop_action_token)
            active.stop_action_token = ""

    async def _configure_bot_commands(self) -> None:
        """Configure the intentionally small Telegram play menu."""
        if not self._app or not self._agent_client:
            return

        agent_command_names: set[str] = set()
        try:
            command_payload = await self._agent_client.list_commands(
                self._default_session_id,
            )
            agent_command_names = {
                _telegram_menu_command_name(str(item.get("command", "")))
                for item in command_payload.get("commands", [])
            }
        except Exception:
            logger.exception("telegram: failed to load agent commands for bot menu")

        menu_names = [
            "start",
            "help",
            "role_bind",
            "sessions",
            "session_create",
            "clear",
        ]
        if "compact" in agent_command_names:
            menu_names.append("compact")
        if self._streaming:
            menu_names.append("stop")
        commands = [
            BotCommand(
                command=name,
                description=_telegram_command_description(_LOCAL_COMMANDS[name]),
            )
            for name in menu_names
        ]

        try:
            await self._request_with_timeout(
                "bot",
                "set_my_commands",
                self._app.bot.set_my_commands(commands),
            )
            logger.info("telegram: bot commands configured count={}", len(commands))
        except Exception:
            logger.exception("telegram: failed to configure bot commands")

    async def _send_session_picker(self, chat_id: str) -> None:
        """发送会话选择菜单。"""
        if not self._app or not self._agent_client:
            await self.send_text(chat_id, "会话菜单暂不可用。")
            return
        current = self.get_session_id(chat_id)
        payload = await self._agent_client.list_sessions(self._workspace_id, self._story_id)
        sessions = payload.get("sessions", [])
        text = self._session_flow.render_session_picker_text(sessions, current)

        await self._request_with_timeout(
            chat_id,
            "send_message",
            self._app.bot.send_message(
                chat_id=int(chat_id),
                text=render_markdown_to_telegram_html(text),
                parse_mode=_TELEGRAM_PARSE_MODE,
                reply_markup=self._session_flow.build_session_picker(chat_id, sessions, current),
            ),
        )

    async def _create_chat_session(self, chat_id: str, title: str) -> str:
        if not self._agent_client:
            raise RuntimeError("Agent client is not bound")
        create_kwargs: dict[str, int] = {}
        if self._player_character_id > 0:
            create_kwargs["player_character_id"] = self._player_character_id
        result = await self._agent_client.create_session(
            self._workspace_id,
            self._story_id,
            title=title.strip(),
            **create_kwargs,
        )
        session_id = str(result.get("session_id") or "")
        if not session_id:
            raise RuntimeError("Agent service did not return session_id")
        return await self._switch_chat_session(chat_id, session_id)

    async def _prompt_session_create(self, chat_id: str) -> None:
        self._session_flow.start_session_create_flow(chat_id)
        await self.send_text(
            chat_id,
            "请输入新会话标题。发送 /cancel 可取消，5 分钟后自动超时。",
        )

    # ── 事件处理 ────────────────────────────────────────────────────────

    async def _on_message(self, update: Update, _context: object) -> None:
        """处理收到的文本消息。"""
        if not update.message or not update.message.text:
            return
        chat_id = str(update.effective_chat.id)
        user_id = str(update.effective_user.id) if update.effective_user else "0"
        text = update.message.text
        logger.info(
            "telegram: received message bot={} chat_id={} user_id={} text={}",
            self._bot_name,
            chat_id,
            user_id,
            _preview_text(text),
        )
        try:
            session_id = self.get_session_id(chat_id)
        except Exception:
            logger.exception("telegram: failed to resolve session chat_id={}", chat_id)
            await self.send_text(chat_id, _GENERIC_FAILURE_TEXT)
            return
        busy = self._turn_flow.busy_reason(chat_id, session_id)
        if busy is not None:
            await self.send_text(chat_id, self._turn_busy_text(busy))
            return
        try:
            if await self._session_flow.handle_plain_text(
                chat_id,
                text,
                send_text=lambda reply: self.send_text(chat_id, reply),
                create_and_switch=lambda title: self._create_chat_session(chat_id, title),
            ):
                logger.info(
                    "telegram: message consumed by session-create flow bot={} chat_id={} user_id={}",
                    self._bot_name,
                    chat_id,
                    user_id,
                )
                return
        except Exception:
            logger.exception(
                "telegram: session-create flow failed bot={} chat_id={} user_id={} text={}",
                self._bot_name,
                chat_id,
                user_id,
                _preview_text(text),
            )
            await self.send_text(chat_id, "会话操作失败，请重试或发送 /cancel。")
            return

        try:
            overview = await self._get_session_overview(chat_id)
        except Exception:
            logger.exception(
                "telegram: player role lookup failed chat_id={} session_id={}",
                chat_id,
                session_id,
            )
            await self.send_text(chat_id, "当前角色状态读取失败，请稍后重试。")
            return
        if overview.get("player_character_status") != "bound":
            await self._send_role_picker(chat_id, overview=overview)
            return

        reservation = self._turn_flow.reserve(chat_id, session_id)
        if not reservation.accepted or reservation.active is None:
            await self.send_text(
                chat_id,
                self._turn_busy_text(reservation.busy_reason),
            )
            return
        active = reservation.active
        if not self._app:
            self._turn_flow.release(active)
            await self.send_text(chat_id, _GENERIC_FAILURE_TEXT)
            return

        coroutine = self._turn_flow.run(active, text)
        try:
            task = self._app.create_task(
                coroutine,
                update=update,
                name=f"telegram:{self._bot_name}:{chat_id}:{active.request_id[:8]}",
            )
        except Exception:
            coroutine.close()
            self._turn_flow.release(active)
            logger.exception(
                "telegram: failed to schedule turn bot={} chat_id={} user_id={} text={}",
                self._bot_name,
                chat_id,
                user_id,
                _preview_text(text),
            )
            await self.send_text(chat_id, _GENERIC_FAILURE_TEXT)
            return
        if not self._turn_flow.attach_task(active, task):
            task.cancel()
            self._turn_flow.release(active)
            await self.send_text(chat_id, _GENERIC_FAILURE_TEXT)
            return
        logger.info(
            "telegram: turn scheduled bot={} chat_id={} user_id={} session_id={} request_id={}",
            self._bot_name,
            chat_id,
            user_id,
            session_id,
            active.request_id[:11],
        )

    async def _on_command(self, update: Update, _context: object) -> None:
        """处理 Telegram 斜杠命令。"""
        if not update.message or not update.message.text:
            return
        chat_id = str(update.effective_chat.id)
        user_id = str(update.effective_user.id) if update.effective_user else "0"
        raw_command = update.message.text.strip()
        command = _normalize_telegram_command(raw_command)

        try:
            session_id = self.get_session_id(chat_id)
        except Exception:
            logger.exception("telegram: failed to resolve command session chat_id={}", chat_id)
            await self.send_text(chat_id, "命令暂不可用。")
            return

        if command == "/stop":
            await self._stop_current_turn(chat_id)
            return
        if self._turn_flow.busy_reason(chat_id, session_id) is not None:
            await self.send_text(chat_id, _COMMAND_BUSY_TEXT)
            return

        if command == "/start":
            await self._on_start(update, _context)
            return

        if command == "/help":
            await self._send_help(chat_id)
            return

        if command == "/role_bind":
            await self._send_role_picker(chat_id)
            return

        if await self._session_flow.handle_command(
            chat_id,
            command,
            send_text=lambda reply: self.send_text(chat_id, reply),
            send_session_picker=lambda: self._send_session_picker(chat_id),
        ):
            return

        if command.startswith("/session_create"):
            parts = command.split(maxsplit=1)
            if len(parts) == 1 or not parts[1].strip():
                await self._prompt_session_create(chat_id)
                return
            title = parts[1].strip()
            try:
                active_session = await self._create_chat_session(chat_id, title)
                await self.send_text(
                    chat_id,
                    f"已新建并进入会话：{title} · {short_session_id(active_session)}",
                )
            except Exception:
                logger.exception(
                    "telegram: session_create failed chat_id={} user_id={} command={}",
                    chat_id,
                    user_id,
                    _preview_text(command),
                )
                await self.send_text(chat_id, "会话创建失败，请稍后重试。")
            return

        if not self._agent_client:
            logger.warning(
                "telegram: command ignored because agent is missing chat_id={} user_id={} command={}",
                chat_id,
                user_id,
                _preview_text(command),
            )
            await self.send_text(chat_id, "命令暂不可用。")
            return

        logger.info(
            "telegram: received command chat_id={} user_id={} command={}",
            chat_id,
            user_id,
            _preview_text(command),
        )
        try:
            result = await self._agent_client.execute_command(
                session_id,
                command,
            )
            handled = bool(result.get("handled", True))
            reply = str(result.get("reply", ""))
            active_session = str(result.get("active_session") or "")
        except Exception:
            logger.exception(
                "telegram: command handler failed chat_id={} user_id={} command={}",
                chat_id,
                user_id,
                _preview_text(command),
            )
            await self.send_text(chat_id, f"命令执行失败: {command.split()[0]}")
            return

        if not handled:
            await self.send_text(chat_id, f"未知命令: {command.split()[0]}")
            return

        if command.startswith("/session_switch ") and reply.startswith("[已切换到会话: "):
            active_session = active_session or command.split(maxsplit=1)[1]
            self._session_flow.pin_session(chat_id, active_session)

        if reply:
            if command.startswith("/role_bind "):
                await self.send_text(chat_id, reply, project_rp=True)
            else:
                await self.send_text(chat_id, reply)

    async def _on_callback_query(self, update: Update, _context: object) -> None:
        """Resolve, gate, claim, and dispatch Telegram callback actions."""
        query = update.callback_query
        if query is None:
            return
        chat_id = str(query.message.chat.id) if query.message and query.message.chat else "0"
        try:
            current_session_id = self.get_session_id(chat_id)
        except Exception:
            await query.answer(_CALLBACK_INVALID_TEXT, show_alert=True)
            return
        resolution = self._action_registry.resolve(
            str(query.data or ""),
            chat_id=chat_id,
            current_session_id=current_session_id,
        )
        if not resolution.resolved or resolution.action is None:
            await query.answer(_CALLBACK_INVALID_TEXT, show_alert=True)
            return
        resolved_action = resolution.action
        if (
            resolved_action.kind != _TURN_ACTION_STOP
            and self._turn_flow.busy_reason(chat_id, current_session_id) is not None
        ):
            await query.answer(_CALLBACK_BUSY_TEXT)
            return
        action = self._action_registry.claim(resolution.token)
        if action is None:
            await query.answer(_CALLBACK_INVALID_TEXT, show_alert=True)
            return
        await query.answer()
        try:
            if action.kind == _TURN_ACTION_STOP:
                await self._stop_current_turn(chat_id)
                return
            if action.kind == PLAY_ACTION_CHOOSE_ROLE:
                await self._send_role_picker(chat_id)
                return
            if action.kind == PLAY_ACTION_OPEN_SESSIONS:
                await self._send_session_picker(chat_id)
                return
            if action.kind == PLAY_ACTION_START:
                overview = await self._get_session_overview(chat_id)
                if overview.get("player_character_status") != "bound":
                    await self._send_role_picker(chat_id, overview=overview)
                else:
                    await self.send_text(chat_id, "准备好了，直接发送你的行动即可。")
                return
            if action.kind == PLAY_ACTION_BIND_ROLE:
                character_id = int(action.payload.get("character_id") or 0)
                if character_id <= 0:
                    raise ValueError("missing character_id")
                await self._bind_player_character(chat_id, character_id)
                return
            handled = await self._session_flow.handle_action(
                action,
                send_text=lambda reply: self.send_text(chat_id, reply),
                switch_session=lambda session_id: self._switch_chat_session(chat_id, session_id),
                create_session=lambda: self._prompt_session_create(chat_id),
            )
        except Exception:
            logger.exception(
                "telegram: callback action failed chat_id={} kind={}",
                chat_id,
                action.kind,
            )
            await self.send_text(chat_id, "会话操作失败，请重新打开菜单。")
            return
        if not handled:
            await self.send_text(chat_id, _CALLBACK_INVALID_TEXT)

    async def _switch_chat_session(self, chat_id: str, session_id: str) -> str:
        if not self._agent_client:
            raise RuntimeError("Agent client is not bound")
        result = await self._agent_client.execute_command(
            self.get_session_id(chat_id),
            f"/session_switch {session_id}",
        )
        active_session = str(result.get("active_session") or "")
        if not bool(result.get("handled", True)) or active_session != session_id:
            raise RuntimeError(str(result.get("reply") or "会话切换失败"))
        self._session_flow.pin_session(chat_id, active_session)
        return active_session

    async def _get_session_overview(
        self,
        chat_id: str,
    ) -> AgentSessionOverviewPayload:
        if not self._agent_client:
            raise RuntimeError("Agent client is not bound")
        return await self._agent_client.get_session_overview(self.get_session_id(chat_id))

    async def _send_entry_card(self, chat_id: str) -> None:
        overview = await self._get_session_overview(chat_id)
        await self.send_text(
            chat_id,
            self._play_flow.render_entry_text(overview),
            reply_markup=self._play_flow.build_entry_keyboard(chat_id, overview),
        )

    async def _send_role_picker(
        self,
        chat_id: str,
        *,
        overview: AgentSessionOverviewPayload | None = None,
    ) -> None:
        current = overview or await self._get_session_overview(chat_id)
        await self.send_text(
            chat_id,
            self._play_flow.render_role_picker_text(current),
            reply_markup=self._play_flow.build_role_picker(chat_id, current),
        )

    async def _bind_player_character(self, chat_id: str, character_id: int) -> None:
        if not self._agent_client:
            raise RuntimeError("Agent client is not bound")
        session_id = self.get_session_id(chat_id)
        result = await self._agent_client.bind_player_character(session_id, character_id)
        player = result.get("player_character") or {}
        player_name = str(player.get("name") or f"角色 {character_id}")
        await self.send_text(chat_id, f"已选择玩家角色：{player_name}。")
        first_message = str(result.get("first_message") or "")
        if first_message:
            await self.send_text(chat_id, first_message, project_rp=True)

    async def _stop_current_turn(self, chat_id: str) -> None:
        if not self._streaming:
            await self.send_text(chat_id, "当前 Bot 未启用流式停止。")
            return
        status = await self._turn_flow.request_stop(chat_id)
        if status == TurnCancelStatus.CANCELLED.value:
            return
        if status in {
            TurnCancelStatus.STALE.value,
            TurnCancelStatus.NOT_RUNNING.value,
        }:
            await self.send_text(chat_id, "本轮已经结束或无法停止。")
            return
        await self.send_text(chat_id, "停止生成失败，请稍后重试。")

    async def _send_help(self, chat_id: str) -> None:
        local_names = [
            "start",
            "help",
            "role_bind",
            "sessions",
            "session_create",
            "cancel",
        ]
        if self._streaming:
            local_names.append("stop")
        commands: dict[str, str] = {
            name: _LOCAL_COMMANDS[name]
            for name in local_names
        }
        degraded = False
        try:
            if not self._agent_client:
                raise RuntimeError("Agent client is not bound")
            payload = await self._agent_client.list_commands(self.get_session_id(chat_id))
            for item in payload.get("commands", []):
                name = _telegram_menu_command_name(str(item.get("command", "")))
                if not name:
                    continue
                commands.setdefault(name, str(item.get("description") or "可用命令"))
        except Exception:
            degraded = True
            logger.exception("telegram: help command lookup failed chat_id={}", chat_id)
        lines = ["可用命令："]
        lines.extend(f"- /{name}: {description}" for name, description in commands.items())
        if degraded:
            lines.extend(["", "Agent 命令列表暂不可用，以上仅显示 Telegram 本地命令。"])
        await self.send_text(chat_id, "\n".join(lines))

    async def _on_start(self, update: Update, _context: object) -> None:
        """处理 /start 命令。"""
        if not update.message:
            return
        chat_id = str(update.effective_chat.id)
        logger.info("telegram: received /start chat_id={}", chat_id)
        try:
            await self._send_entry_card(chat_id)
        except Exception:
            logger.exception("telegram: start entry failed chat_id={}", chat_id)
            await self.send_text(chat_id, "游玩入口暂不可用，请稍后重试。")

    async def _on_error(self, _update: object, context: object) -> None:
        """记录 python-telegram-bot 调用链中的异常。"""
        error = getattr(context, "error", None)
        if error is None:
            logger.error("telegram: application error without exception payload")
            return
        logger.opt(exception=error).error("telegram: application error")

    @staticmethod
    def _turn_busy_text(reason: TelegramTurnBusyReason | None) -> str:
        if reason == TelegramTurnBusyReason.SESSION:
            return _SESSION_BUSY_TEXT
        return _CHAT_BUSY_TEXT
