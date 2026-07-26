"""TelegramAdapter — 基于 python-telegram-bot 的 Telegram 渠道适配器。

支持两种模式：
- **流式（streaming=True）**：通过 ``TelegramTurnFlow`` 逐段编辑消息实现实时输出
- **缓冲（streaming=False）**：仍使用可取消 SSE，仅在终态一次性展示完整回复

用法::

    from channels import TelegramAdapter

    adapter = TelegramAdapter(token="env:TELEGRAM_BOT_TOKEN", streaming=True)
    adapter.bind_agent_client(client)
    await adapter.start()
"""

from __future__ import annotations

import asyncio
import html
import re
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from loguru import logger
from telegram import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest, RetryAfter, TelegramError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from agent_service.client import AgentClientError
from channels.base import ChannelAdapter
from channels.telegram.action_registry import (
    TelegramActionRegistry,
    TelegramCallbackAction,
)
from channels.telegram.play_flow import (
    PLAY_ACTION_BIND_ROLE,
    PLAY_ACTION_CHOOSE_ROLE,
    PLAY_ACTION_OPEN_SESSIONS,
    PLAY_ACTION_START,
    TelegramPlayFlow,
)
from channels.telegram.reference_flow import (
    REFERENCE_ACTION_KINDS,
    REFERENCE_ACTION_ROOT,
    TelegramReferenceFlow,
    TelegramReferenceView,
)
from channels.telegram.render import (
    chunk_rendered_text,
    project_rp_text,
    render_markdown_to_telegram_html,
)
from channels.telegram.session_flow import (
    SESSION_ACTION_CREATE,
    SESSION_ACTION_SWITCH,
    TelegramSessionFlow,
    short_session_id,
)
from channels.telegram.turn_flow import (
    ActiveTelegramTurn,
    TelegramTurnBusyReason,
    TelegramTurnFlow,
)
from rpg_core.agent.protocol import TurnCancelStatus
from rpg_core.session.reference import (
    SessionReferenceLocator,
    SessionReferenceNotFoundError,
    SessionReferenceResourceDisabledError,
    SessionReferenceUnavailableError,
)

if TYPE_CHECKING:
    from agent_service.client import AgentClient
    from agent_service.schemas import AgentSessionOverviewPayload
    from rpg_core.session.reference import SessionReferenceReader

_TELEGRAM_PARSE_MODE = "HTML"
_TELEGRAM_COMMAND_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_CALLBACK_INVALID_TEXT = "该菜单已失效，请重新打开。"
_CALLBACK_BUSY_TEXT = "当前会话正在生成，请完成后再操作。"
_CHAT_BUSY_TEXT = "当前消息仍在生成，请等待完成后再发送。"
_SESSION_BUSY_TEXT = "当前会话正在处理另一条消息，请稍后再试。"
_COMMAND_BUSY_TEXT = "当前会话正在生成，请完成后再执行命令。"
_GENERIC_FAILURE_TEXT = "处理消息失败，请稍后重试。"
_SESSION_UNAVAILABLE_TEXT = "当前会话已删除或暂不可用。请选择其它会话，或新建并进入会话。"
_SESSION_LIST_UNAVAILABLE_TEXT = (
    "会话列表暂不可用。你仍可点击“新建并进入”创建会话，或稍后发送 /sessions 重试。"
)
_TURN_ACTION_STOP = "turn_stop"
_TERMINAL_RETRY_ATTEMPTS = 2
_TERMINAL_RETRY_MAX_WAIT_SECONDS = 10.0
_SESSION_RECOVERY_ACTIONS = frozenset({
    _TURN_ACTION_STOP,
    PLAY_ACTION_OPEN_SESSIONS,
    SESSION_ACTION_CREATE,
    SESSION_ACTION_SWITCH,
})
_LOCAL_COMMANDS = {
    "start": "打开游玩入口",
    "info": "查看当前会话资料",
    "help": "查看全部可用命令",
    "role_bind": "选择或切换玩家角色",
    "sessions": "查看并切换会话",
    "session_create": "新建并进入会话",
    "clear": "重置当前会话并重新开始游戏",
    "compact": "压缩当前会话上下文",
    "stop": "停止当前生成",
    "cancel": "取消正在输入的新会话标题",
}


class _TelegramHTMLTextExtractor(HTMLParser):
    """Best-effort plain-text projection for Telegram HTML fallback."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(
        self,
        tag: str,
        _attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() == "br":
            self.parts.append("\n")


def _telegram_html_to_plain_text(text: str) -> str:
    parser = _TelegramHTMLTextExtractor()
    try:
        parser.feed(str(text))
        parser.close()
        return "".join(parser.parts)
    except Exception:
        return html.unescape(re.sub(r"<[^>]*>", "", str(text)))


class _TelegramSessionUnavailableError(RuntimeError):
    """The current or requested catalog session cannot be used."""


class _TelegramSessionTargetError(RuntimeError):
    """A switch target is outside this bot's configured workspace/story."""


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
        ``False`` 缓冲同一 SSE 请求并在 DONE 后一次性展示完整回复。
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
        shutdown_grace_ms: int = 15_000,
        agent_client: AgentClient | None = None,
        workspace: str | None = None,
        workspace_id: str | None = None,
        story_id: int | None = None,
        player_character_id: int = 0,
        session_id: str | None = None,
        session_title: str | None = None,
        reference_menu_enabled: bool = False,
        reference_reader: SessionReferenceReader | None = None,
    ) -> None:
        super().__init__()
        self._bot_name = bot_name
        self._token = token
        self._streaming = streaming
        self._proxy = proxy
        self._stream_edit_interval = max(0, stream_edit_interval_ms) / 1000.0
        self._stream_edit_min_chars = max(1, stream_edit_min_chars)
        self._request_timeout = max(0, request_timeout_ms) / 1000.0
        self._shutdown_grace = max(1, int(shutdown_grace_ms)) / 1000.0
        self._workspace_override = (workspace or "").strip() or None
        self._workspace_id = (workspace_id or "").strip()
        self._story_id = int(story_id or 0)
        self._player_character_id = int(player_character_id or 0)
        self._default_session_id = (session_id or "").strip()
        self._session_title = (session_title or bot_name or "Telegram").strip()
        self._reference_menu_enabled = bool(reference_menu_enabled)
        self._app: Application | None = None
        self._action_registry = TelegramActionRegistry()
        self._session_flow = TelegramSessionFlow(self._action_registry)
        self._play_flow = TelegramPlayFlow(self._action_registry)
        self._reference_flow = (
            TelegramReferenceFlow(self._action_registry, reference_reader)
            if reference_reader is not None
            else None
        )
        self._turn_flow = TelegramTurnFlow(
            presenter=self,
            streaming=self._streaming,
            stream_edit_interval_seconds=self._stream_edit_interval,
            stream_edit_min_chars=self._stream_edit_min_chars,
            stop_markup_factory=self._build_stop_markup,
            terminal_cleanup=self._cleanup_turn_action,
            active_session_callback=self._sync_active_session,
            shutdown_grace_seconds=self._shutdown_grace,
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

    def bind_reference_reader(self, reader: SessionReferenceReader) -> None:
        """Bind the shared read-only Session reference boundary."""
        self._reference_flow = TelegramReferenceFlow(
            self._action_registry,
            reader,
        )

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 Telegram 长轮询。"""
        logger.info(
            "telegram: preparing adapter bot={} "
            "(streaming={}, proxy={}, interval_ms={}, min_chars={}, "
            "request_timeout_ms={}, shutdown_grace_ms={}, reference_menu={})",
            self._bot_name,
            self._streaming,
            self._proxy or "<disabled>",
            int(self._stream_edit_interval * 1000),
            self._stream_edit_min_chars,
            int(self._request_timeout * 1000),
            int(self._shutdown_grace * 1000),
            self._reference_menu_enabled,
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

    async def _terminal_request(
        self,
        chat_id: str,
        action: str,
        request_factory,
    ):
        """Run a terminal Telegram write with bounded RetryAfter handling."""
        total_wait = 0.0
        for attempt in range(_TERMINAL_RETRY_ATTEMPTS + 1):
            try:
                awaitable = request_factory()
                if self._request_timeout <= 0:
                    return await awaitable
                return await asyncio.wait_for(
                    awaitable,
                    timeout=self._request_timeout,
                )
            except RetryAfter as exc:
                raw_delay = exc.retry_after
                delay = (
                    float(raw_delay.total_seconds())
                    if hasattr(raw_delay, "total_seconds")
                    else float(raw_delay)
                )
                delay = max(0.0, delay)
                can_retry = (
                    attempt < _TERMINAL_RETRY_ATTEMPTS
                    and total_wait + delay <= _TERMINAL_RETRY_MAX_WAIT_SECONDS
                )
                logger.warning(
                    "telegram: terminal {} rate limited bot={} chat_id={} "
                    "retry_after={}s attempt={} retry={}",
                    action,
                    self._bot_name,
                    chat_id,
                    delay,
                    attempt + 1,
                    can_retry,
                )
                if not can_retry:
                    return None
                total_wait += delay
                await asyncio.sleep(delay)
            except BadRequest:
                raise
            except (TimeoutError, TimedOut) as exc:
                logger.warning(
                    "telegram: terminal {} timed out bot={} chat_id={} "
                    "timeout_ms={} error_type={}",
                    action,
                    self._bot_name,
                    chat_id,
                    int(self._request_timeout * 1000),
                    type(exc).__name__,
                )
                return None
            except (TelegramError, OSError) as exc:
                logger.warning(
                    "telegram: terminal {} failed bot={} chat_id={} error_type={}",
                    action,
                    self._bot_name,
                    chat_id,
                    type(exc).__name__,
                )
                return None
            except Exception:
                logger.exception(
                    "telegram: terminal {} unexpected failure bot={} chat_id={}",
                    action,
                    self._bot_name,
                    chat_id,
                )
                return None
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
        terminal: bool = False,
    ) -> int | None:
        """Send one already-rendered Telegram HTML message."""
        if not self._app:
            logger.warning("telegram: send_html skipped because application is not ready")
            return None
        if len(text) > 4096:
            raise ValueError("Telegram HTML message exceeds 4096 characters")
        send_kwargs: dict[str, object] = {
            "chat_id": int(chat_id),
            "text": text,
            "parse_mode": _TELEGRAM_PARSE_MODE,
        }
        if reply_markup is not None:
            send_kwargs["reply_markup"] = reply_markup
        if terminal:
            try:
                message = await self._terminal_request(
                    chat_id,
                    "send_message",
                    lambda: self._app.bot.send_message(**send_kwargs),
                )
            except BadRequest as exc:
                logger.warning(
                    "telegram: terminal send_message markup rejected; "
                    "retrying plain text bot={} chat_id={} error_type={}",
                    self._bot_name,
                    chat_id,
                    type(exc).__name__,
                )
                fallback_kwargs = dict(send_kwargs)
                fallback_kwargs["text"] = _telegram_html_to_plain_text(text)
                fallback_kwargs.pop("parse_mode", None)
                try:
                    message = await self._terminal_request(
                        chat_id,
                        "send_message_plain_fallback",
                        lambda: self._app.bot.send_message(**fallback_kwargs),
                    )
                except BadRequest as fallback_exc:
                    logger.warning(
                        "telegram: terminal send_message plain fallback rejected "
                        "bot={} chat_id={} error_type={}",
                        self._bot_name,
                        chat_id,
                        type(fallback_exc).__name__,
                    )
                    return None
        else:
            message = await self._request_with_timeout(
                chat_id,
                "send_message",
                self._app.bot.send_message(**send_kwargs),
            )
        message_id = getattr(message, "message_id", None)
        return int(message_id) if message_id is not None else None

    async def edit_html(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        terminal: bool = False,
    ) -> bool:
        """Edit one Telegram message with already-rendered HTML."""
        if not self._app:
            return False
        if len(text) > 4096:
            raise ValueError("Telegram HTML message exceeds 4096 characters")
        edit_kwargs: dict[str, object] = {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "text": text,
            "parse_mode": _TELEGRAM_PARSE_MODE,
        }
        if reply_markup is not None:
            edit_kwargs["reply_markup"] = reply_markup
        if terminal:
            try:
                result = await self._terminal_request(
                    chat_id,
                    "edit_message_text",
                    lambda: self._app.bot.edit_message_text(**edit_kwargs),
                )
            except BadRequest as exc:
                if "Message is not modified" in str(exc):
                    return True
                logger.warning(
                    "telegram: terminal edit_message_text markup rejected; "
                    "retrying plain text bot={} chat_id={} error_type={}",
                    self._bot_name,
                    chat_id,
                    type(exc).__name__,
                )
                fallback_kwargs = dict(edit_kwargs)
                fallback_kwargs["text"] = _telegram_html_to_plain_text(text)
                fallback_kwargs.pop("parse_mode", None)
                try:
                    result = await self._terminal_request(
                        chat_id,
                        "edit_message_text_plain_fallback",
                        lambda: self._app.bot.edit_message_text(**fallback_kwargs),
                    )
                except BadRequest as fallback_exc:
                    if "Message is not modified" in str(fallback_exc):
                        return True
                    logger.warning(
                        "telegram: terminal edit_message_text plain fallback rejected "
                        "bot={} chat_id={} error_type={}",
                        self._bot_name,
                        chat_id,
                        type(fallback_exc).__name__,
                    )
                    return False
        else:
            result = await self._request_with_timeout(
                chat_id,
                "edit_message_text",
                self._app.bot.edit_message_text(
                    **edit_kwargs,
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
        if self._reference_menu_enabled:
            menu_names.insert(1, "info")
        if "compact" in agent_command_names:
            menu_names.append("compact")
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

    async def _send_session_picker(
        self,
        chat_id: str,
        *,
        session_unavailable: bool = False,
    ) -> None:
        """发送会话选择菜单。"""
        if not self._app or not self._agent_client:
            await self.send_text(chat_id, "会话菜单暂不可用。")
            return
        app = self._app
        current = self.get_session_id(chat_id)
        list_failed = False
        try:
            payload = await self._agent_client.list_sessions(
                self._workspace_id,
                self._story_id,
            )
            sessions = payload.get("sessions", [])
            if not isinstance(sessions, list):
                raise TypeError("Agent service returned a non-list sessions payload")
        except Exception:
            logger.exception(
                "telegram: session picker lookup failed "
                "bot={} chat_id={} workspace_id={} story_id={}",
                self._bot_name,
                chat_id,
                self._workspace_id,
                self._story_id,
            )
            sessions = []
            list_failed = True
        text = (
            _SESSION_LIST_UNAVAILABLE_TEXT
            if list_failed
            else self._session_flow.render_session_picker_text(sessions, current)
        )
        if session_unavailable:
            text = f"{_SESSION_UNAVAILABLE_TEXT}\n\n{text}"

        await self._request_with_timeout(
            chat_id,
            "send_message",
            app.bot.send_message(
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
        try:
            return await self._switch_chat_session(chat_id, session_id)
        except BaseException:
            try:
                await self._agent_client.delete_session(session_id)
            except Exception:
                logger.exception(
                    "telegram: failed to clean up session after switch failure "
                    "chat_id={} session_id={}",
                    chat_id,
                    session_id,
                )
            raise

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
        except Exception as exc:
            if self._is_session_unavailable_error(exc):
                logger.info(
                    "telegram: blocking message for unavailable session "
                    "chat_id={} session_id={}",
                    chat_id,
                    session_id,
                )
                await self._send_session_picker(
                    chat_id,
                    session_unavailable=True,
                )
                return
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

        command_parts = command.split(maxsplit=1)
        command_name = command_parts[0] if command_parts else ""

        if command == "/info":
            await self._send_reference_root(chat_id)
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

        if command_name == "/session_create":
            if len(command_parts) == 1 or not command_parts[1].strip():
                await self._prompt_session_create(chat_id)
                return
            title = command_parts[1].strip()
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

        if command_name == "/session_switch":
            if len(command_parts) == 1 or not command_parts[1].strip():
                await self._send_session_picker(chat_id)
                return
            target_session_id = command_parts[1].split(maxsplit=1)[0]
            try:
                active_session = await self._switch_chat_session(
                    chat_id,
                    target_session_id,
                )
            except Exception:
                logger.exception(
                    "telegram: session_switch failed "
                    "chat_id={} user_id={} target_session_id={}",
                    chat_id,
                    user_id,
                    target_session_id,
                )
                try:
                    await self._get_session_overview(chat_id)
                except Exception as current_exc:
                    if self._is_session_unavailable_error(current_exc):
                        await self._send_session_picker(
                            chat_id,
                            session_unavailable=True,
                        )
                        return
                await self.send_text(chat_id, "会话切换失败，请重新选择。")
                await self._send_session_picker(chat_id)
                return
            await self.send_text(chat_id, f"[已切换到会话: {active_session}]")
            return

        try:
            await self._get_session_overview(chat_id)
        except Exception as exc:
            if self._is_session_unavailable_error(exc):
                await self._send_session_picker(
                    chat_id,
                    session_unavailable=True,
                )
                return
            logger.exception(
                "telegram: command session lookup failed "
                "chat_id={} user_id={} command={}",
                chat_id,
                user_id,
                _preview_text(command),
            )
            await self.send_text(chat_id, "当前会话状态读取失败，请稍后重试。")
            return

        if command == "/help":
            await self._send_help(chat_id)
            return

        if command == "/role_bind":
            await self._send_role_picker(chat_id)
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

        if active_session:
            self._session_flow.pin_session_if_current(
                chat_id,
                active_session,
                expected_current_session_id=session_id,
                default_session_id=self._default_session_id,
            )

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
            await self._answer_callback_query(
                query,
                chat_id,
                _CALLBACK_INVALID_TEXT,
                show_alert=True,
            )
            return
        resolution = self._action_registry.resolve(
            str(query.data or ""),
            chat_id=chat_id,
            current_session_id=current_session_id,
        )
        if not resolution.resolved or resolution.action is None:
            await self._answer_callback_query(
                query,
                chat_id,
                _CALLBACK_INVALID_TEXT,
                show_alert=True,
            )
            return
        resolved_action = resolution.action
        if (
            resolved_action.kind != _TURN_ACTION_STOP
            and resolved_action.kind not in REFERENCE_ACTION_KINDS
            and self._turn_flow.busy_reason(chat_id, current_session_id) is not None
        ):
            await self._answer_callback_query(
                query,
                chat_id,
                _CALLBACK_BUSY_TEXT,
            )
            return
        if (
            resolved_action.kind not in _SESSION_RECOVERY_ACTIONS
            and resolved_action.kind not in REFERENCE_ACTION_KINDS
        ):
            try:
                await self._get_session_overview(chat_id)
            except Exception as exc:
                if self._is_session_unavailable_error(exc):
                    await self._answer_callback_query(query, chat_id)
                    await self._send_session_picker(
                        chat_id,
                        session_unavailable=True,
                    )
                    return
                logger.exception(
                    "telegram: callback session lookup failed "
                    "chat_id={} kind={}",
                    chat_id,
                    resolved_action.kind,
                )
                await self._answer_callback_query(
                    query,
                    chat_id,
                    _CALLBACK_INVALID_TEXT,
                    show_alert=True,
                )
                return
        action = self._action_registry.claim(resolution.token)
        if action is None:
            await self._answer_callback_query(
                query,
                chat_id,
                _CALLBACK_INVALID_TEXT,
                show_alert=True,
            )
            return
        if action.kind in REFERENCE_ACTION_KINDS:
            # The selected token was consumed by ``claim``. Remove the rest of
            # the old menu before the first async read so two sibling buttons
            # cannot race to replace the same Telegram message.
            self._action_registry.invalidate_view_group(action.view_group_id)
        await self._answer_callback_query(query, chat_id)
        if action.kind in REFERENCE_ACTION_KINDS:
            await self._handle_reference_action(query, chat_id, action)
            return
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

    async def _answer_callback_query(
        self,
        query: CallbackQuery,
        chat_id: str,
        text: str | None = None,
        *,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledge a callback without aborting an already-resolved action."""
        try:
            if show_alert:
                await query.answer(text, show_alert=True)
            elif text is not None:
                await query.answer(text)
            else:
                await query.answer()
            return True
        except (TelegramError, OSError) as exc:
            logger.warning(
                "telegram: callback answer failed "
                "bot={} chat_id={} error_type={}",
                self._bot_name,
                chat_id,
                type(exc).__name__,
            )
        except Exception:
            logger.exception(
                "telegram: callback answer unexpected failure "
                "bot={} chat_id={}",
                self._bot_name,
                chat_id,
            )
        return False

    async def _switch_chat_session(self, chat_id: str, session_id: str) -> str:
        if not self._agent_client:
            raise RuntimeError("Agent client is not bound")
        target_session_id = str(session_id).strip()
        await self._validate_switch_target(target_session_id)
        source_session_id = self.get_session_id(chat_id)
        try:
            result = await self._agent_client.execute_command(
                source_session_id,
                f"/session_switch {target_session_id}",
            )
        except AgentClientError as exc:
            if (
                source_session_id == target_session_id
                or not self._is_session_unavailable_error(exc)
            ):
                raise
            # The source may have been deleted by another channel. The target
            # was independently validated above, so ask its own mailbox to
            # confirm the typed locator rather than silently falling back.
            result = await self._agent_client.execute_command(
                target_session_id,
                f"/session_switch {target_session_id}",
            )
        active_session = str(result.get("active_session") or "")
        if (
            not bool(result.get("handled", True))
            or active_session != target_session_id
        ):
            raise RuntimeError(str(result.get("reply") or "会话切换失败"))
        self._session_flow.pin_session(chat_id, active_session)
        if active_session != source_session_id:
            self._action_registry.invalidate_chat(chat_id)
        return active_session

    async def _validate_switch_target(
        self,
        session_id: str,
    ) -> AgentSessionOverviewPayload:
        if not self._agent_client:
            raise RuntimeError("Agent client is not bound")
        if not session_id:
            raise _TelegramSessionTargetError("目标会话 ID 不能为空")
        overview = await self._agent_client.get_session_overview(session_id)
        self._require_overview_locator(
            overview,
            expected_session_id=session_id,
            error_type=_TelegramSessionTargetError,
        )
        return overview

    async def _get_session_overview(
        self,
        chat_id: str,
    ) -> AgentSessionOverviewPayload:
        if not self._agent_client:
            raise RuntimeError("Agent client is not bound")
        session_id = self.get_session_id(chat_id)
        overview = await self._agent_client.get_session_overview(session_id)
        self._require_overview_locator(
            overview,
            expected_session_id=session_id,
            error_type=_TelegramSessionUnavailableError,
        )
        return overview

    def _require_overview_locator(
        self,
        overview: AgentSessionOverviewPayload,
        *,
        expected_session_id: str,
        error_type: type[RuntimeError],
    ) -> None:
        returned_session_id = str(overview.get("session_id") or "")
        returned_workspace_id = str(overview.get("workspace_id") or "")
        try:
            returned_story_id = int(overview.get("story_id") or 0)
        except (TypeError, ValueError):
            returned_story_id = 0
        if (
            returned_session_id != expected_session_id
            or returned_workspace_id != self._workspace_id
            or returned_story_id != self._story_id
        ):
            raise error_type(
                "会话定位与当前 Telegram Bot 的 workspace/story 不一致"
            )

    def _sync_active_session(
        self,
        active: ActiveTelegramTurn,
        session_id: str,
    ) -> None:
        pinned = self._session_flow.pin_session_if_current(
            active.chat_id,
            session_id,
            expected_current_session_id=active.session_id,
            default_session_id=self._default_session_id,
        )
        if pinned and session_id != active.session_id:
            self._action_registry.invalidate_chat(active.chat_id)
        if not pinned:
            logger.warning(
                "telegram: ignored stale active-session locator "
                "chat_id={} source_session_id={} target_session_id={}",
                active.chat_id,
                active.session_id,
                session_id,
            )

    @staticmethod
    def _is_session_unavailable_error(exc: BaseException) -> bool:
        if isinstance(exc, _TelegramSessionUnavailableError):
            return True
        if not isinstance(exc, AgentClientError):
            return False
        return exc.status_code in {404, 409}

    def _reference_locator(self, chat_id: str) -> SessionReferenceLocator:
        return SessionReferenceLocator(
            session_id=self.get_session_id(chat_id),
            workspace_id=self._workspace_id,
            story_id=self._story_id,
        )

    async def _send_reference_root(self, chat_id: str) -> None:
        if not self._reference_menu_enabled:
            await self.send_text(chat_id, "资料菜单未启用。")
            return
        flow = self._reference_flow
        if flow is None:
            await self.send_text(
                chat_id,
                "资料读取暂不可用，聊天功能不受影响。",
            )
            return
        locator = self._reference_locator(chat_id)
        try:
            view = await flow.render_root(locator, chat_id)
        except SessionReferenceUnavailableError:
            await self._send_session_picker(
                chat_id,
                session_unavailable=True,
            )
            return
        except Exception:
            logger.exception(
                "telegram: reference root failed bot={} chat_id={} session_id={}",
                self._bot_name,
                chat_id,
                locator.session_id,
            )
            retry_action = self._action_registry.create(
                kind=REFERENCE_ACTION_ROOT,
                chat_id=chat_id,
                session_id=locator.session_id,
            )
            view = flow.render_failure(
                locator,
                chat_id,
                retry_action,
                text="资料暂时无法读取，请稍后重试。",
            )
        await self._present_reference_view(chat_id, view)

    async def _handle_reference_action(
        self,
        query: CallbackQuery,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> None:
        flow = self._reference_flow
        if not self._reference_menu_enabled:
            self._action_registry.invalidate_view_group(action.view_group_id)
            await self.send_text(chat_id, "资料菜单未启用。")
            return
        if flow is None:
            self._action_registry.invalidate_view_group(action.view_group_id)
            await self.send_text(
                chat_id,
                "资料读取暂不可用，聊天功能不受影响。",
            )
            return

        locator = self._reference_locator(chat_id)
        try:
            view = await flow.render_action(locator, chat_id, action)
        except SessionReferenceUnavailableError:
            self._action_registry.invalidate_view_group(action.view_group_id)
            await self._send_session_picker(
                chat_id,
                session_unavailable=True,
            )
            return
        except SessionReferenceNotFoundError:
            view = flow.render_failure(
                locator,
                chat_id,
                action,
                text="内容已变化或不存在，请刷新列表后重新选择。",
                content_changed=True,
            )
        except SessionReferenceResourceDisabledError:
            view = flow.render_failure(
                locator,
                chat_id,
                action,
                text="该资料分类当前未开放。",
                content_changed=True,
            )
        except Exception:
            logger.exception(
                "telegram: reference action failed "
                "bot={} chat_id={} session_id={} kind={}",
                self._bot_name,
                chat_id,
                locator.session_id,
                action.kind,
            )
            view = flow.render_failure(
                locator,
                chat_id,
                action,
                text="该资料暂时无法读取，请稍后重试。",
            )

        raw_message_id = (
            query.message.message_id
            if query.message is not None
            else None
        )
        message_id = (
            raw_message_id
            if isinstance(raw_message_id, int)
            else None
        )
        await self._present_reference_view(
            chat_id,
            view,
            message_id=message_id,
            previous_view_group_id=action.view_group_id,
        )

    async def _present_reference_view(
        self,
        chat_id: str,
        view: TelegramReferenceView,
        *,
        message_id: int | None = None,
        previous_view_group_id: str | None = None,
    ) -> bool:
        delivered = False
        if message_id is not None:
            delivered = await self.edit_html(
                chat_id,
                message_id,
                view.html,
                reply_markup=view.reply_markup,
            )
        if not delivered:
            sent_message_id = await self.send_html(
                chat_id,
                view.html,
                reply_markup=view.reply_markup,
            )
            delivered = sent_message_id is not None
        if delivered:
            self._action_registry.invalidate_view_group(
                previous_view_group_id,
            )
            return True
        self._action_registry.invalidate_view_group(view.view_group_id)
        return False

    async def _send_entry_card(self, chat_id: str) -> None:
        overview = await self._get_session_overview(chat_id)
        await self.send_text(
            chat_id,
            self._play_flow.render_entry_text(overview),
            reply_markup=self._play_flow.build_entry_keyboard(
                chat_id,
                overview,
                reference_menu_enabled=self._reference_menu_enabled,
            ),
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
        if self._reference_menu_enabled:
            local_names.insert(1, "info")
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
        except Exception as exc:
            if self._is_session_unavailable_error(exc):
                await self._send_session_picker(
                    chat_id,
                    session_unavailable=True,
                )
                return
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
