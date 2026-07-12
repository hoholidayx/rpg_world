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
from telegram import BotCommand, Update
from telegram.error import BadRequest, RetryAfter, TelegramError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from channels.base import ChannelAdapter
from channels.telegram.action_registry import TelegramActionRegistry
from channels.telegram.render import (
    chunk_rendered_text,
    render_markdown_to_telegram_html,
)
from channels.telegram.session_flow import TelegramSessionFlow
from channels.telegram.turn_flow import (
    TelegramTurnBusyReason,
    TelegramTurnFlow,
)

if TYPE_CHECKING:
    from agent_service.client import AgentClient

_TELEGRAM_PARSE_MODE = "HTML"
_TELEGRAM_COMMAND_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_CALLBACK_INVALID_TEXT = "该菜单已失效，请重新打开。"
_CALLBACK_BUSY_TEXT = "当前会话正在生成，请完成后再操作。"
_CHAT_BUSY_TEXT = "当前消息仍在生成，请等待完成后再发送。"
_SESSION_BUSY_TEXT = "当前会话正在处理另一条消息，请稍后再试。"
_COMMAND_BUSY_TEXT = "当前会话正在生成，请完成后再执行命令。"
_GENERIC_FAILURE_TEXT = "处理消息失败，请稍后重试。"


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
        auto_pin_created_session: bool = False,
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
        self._auto_pin_created_session = auto_pin_created_session
        self._workspace_override = (workspace or "").strip() or None
        self._workspace_id = (workspace_id or "").strip()
        self._story_id = int(story_id or 0)
        self._player_character_id = int(player_character_id or 0)
        self._default_session_id = (session_id or "").strip()
        self._session_title = (session_title or bot_name or "Telegram").strip()
        self._app: Application | None = None
        self._action_registry = TelegramActionRegistry()
        self._session_flow = TelegramSessionFlow(self._action_registry)
        self._turn_flow = TelegramTurnFlow(
            presenter=self,
            streaming=self._streaming,
            stream_edit_interval_seconds=self._stream_edit_interval,
            stream_edit_min_chars=self._stream_edit_min_chars,
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

    async def send_text(self, chat_id: str, text: str) -> None:
        """发送完整文本消息。超出 4096 字符自动分块。"""
        if not self._app:
            logger.warning("telegram: send_text skipped because application is not ready")
            return
        rendered = render_markdown_to_telegram_html(text)
        logger.debug(
            "telegram: sending text bot={} chat_id={} chunks={} preview={}",
            self._bot_name,
            chat_id,
            len(chunk_rendered_text(rendered)),
            _preview_text(text),
        )
        for chunk in chunk_rendered_text(rendered):
            await self.send_html(chat_id, chunk)

    async def send_html(self, chat_id: str, text: str) -> int | None:
        """Send one already-rendered Telegram HTML message."""
        if not self._app:
            logger.warning("telegram: send_html skipped because application is not ready")
            return None
        message = await self._request_with_timeout(
            chat_id,
            "send_message",
            self._app.bot.send_message(
                chat_id=int(chat_id),
                text=text,
                parse_mode=_TELEGRAM_PARSE_MODE,
            ),
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

    async def _configure_bot_commands(self) -> None:
        """把 agent 的命令列表同步到 Telegram bot 菜单。"""
        if not self._app or not self._agent_client:
            return

        commands = [
            BotCommand(command="start", description="开始对话"),
        ]
        command_payload = await self._agent_client.list_commands(
            self._default_session_id,
        )
        raw_commands = command_payload.get("commands", [])
        for cmd in raw_commands:
            command_name = _telegram_menu_command_name(str(cmd.get("command", "")))
            if not command_name:
                continue
            commands.append(
                BotCommand(
                    command=command_name,
                    description=_telegram_command_description(str(cmd.get("description", ""))),
                )
            )

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
        sessions = [str(item) for item in payload.get("sessions", [])]
        text = self._session_flow.render_session_picker_text(sessions, current)

        await self._request_with_timeout(
            chat_id,
            "send_message",
            self._app.bot.send_message(
                chat_id=int(chat_id),
                text=text,
                parse_mode=_TELEGRAM_PARSE_MODE,
                reply_markup=self._session_flow.build_session_picker(chat_id, sessions, current),
            ),
        )

    async def _create_chat_session(self, chat_id: str, title: str | None = None) -> None:
        if not self._agent_client:
            await self.send_text(chat_id, "会话创建暂不可用。")
            return
        create_kwargs = {}
        if self._player_character_id > 0:
            create_kwargs["player_character_id"] = self._player_character_id
        result = await self._agent_client.create_session(
            self._workspace_id,
            self._story_id,
            title=(title or self._session_title or "").strip(),
            **create_kwargs,
        )
        session_id = str(result.get("session_id") or "")
        if not session_id:
            await self.send_text(chat_id, "会话创建失败：服务未返回 session_id。")
            return
        self._session_flow.maybe_pin_created_session(
            chat_id,
            session_id,
            auto_pin=self._auto_pin_created_session,
        )
        suffix = "，已切换到该会话" if self._auto_pin_created_session else ""
        await self.send_text(chat_id, f"[会话已创建: {session_id}{suffix}]")

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
                agent_client=self._agent_client,
                workspace_id=self._workspace_id,
                story_id=self._story_id,
                send_text=lambda reply: self.send_text(chat_id, reply),
                auto_pin_created_session=self._auto_pin_created_session,
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
        if self._turn_flow.busy_reason(chat_id, session_id) is not None:
            await self.send_text(chat_id, _COMMAND_BUSY_TEXT)
            return

        if command == "/start":
            await self._on_start(update, _context)
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
            title = parts[1].strip() if len(parts) > 1 else self._session_title
            try:
                await self._create_chat_session(chat_id, title=title)
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
        if self._turn_flow.busy_reason(chat_id, current_session_id) is not None:
            await query.answer(_CALLBACK_BUSY_TEXT)
            return
        action = self._action_registry.claim(resolution.token)
        if action is None:
            await query.answer(_CALLBACK_INVALID_TEXT, show_alert=True)
            return
        await query.answer()
        try:
            handled = await self._session_flow.handle_action(
                action,
                send_text=lambda reply: self.send_text(chat_id, reply),
                switch_session=lambda session_id: self._switch_chat_session(chat_id, session_id),
                create_session=lambda: self._create_chat_session(chat_id),
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
        active_session = str(result.get("active_session") or session_id)
        self._session_flow.pin_session(chat_id, active_session)
        return active_session

    async def _on_start(self, update: Update, _context: object) -> None:
        """处理 /start 命令。"""
        if not update.message:
            return
        chat_id = str(update.effective_chat.id)
        logger.info("telegram: received /start chat_id={}", chat_id)
        await self.send_text(chat_id, "欢迎使用 RPG World！发送消息开始冒险。")

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
