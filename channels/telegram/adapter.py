"""TelegramAdapter — 基于 python-telegram-bot 的 Telegram 渠道适配器。

支持两种模式：
- **流式（streaming=True）**：通过 ``send_delta`` 逐段编辑消息实现实时输出
- **非流式（streaming=False）**：一次性通过 ``send_text`` 发送完整回复

用法::

    from rpg_world.channels import TelegramAdapter

    adapter = TelegramAdapter(token="YOUR_BOT_TOKEN", streaming=True)
    adapter.bind_agent(agent)
    await adapter.start()
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger
from telegram import Update
from telegram.error import BadRequest, RetryAfter
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from rpg_world.channels.base import ChannelAdapter
from rpg_world.channels.telegram.render import (
    chunk_rendered_text,
    render_markdown_to_telegram_html,
)

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.agent import RPGGameAgent

_TELEGRAM_PARSE_MODE = "HTML"


def _preview_text(text: str, limit: int = 120) -> str:
    """返回适合日志输出的短文本预览。"""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


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
    agent:
        可选的 RPGGameAgent 实例。
    """

    name = "telegram"

    def __init__(
        self,
        token: str,
        *,
        streaming: bool = True,
        proxy: str = "",
        stream_edit_interval_ms: int = 800,
        stream_edit_min_chars: int = 24,
        request_timeout_ms: int = 5000,
        agent: RPGGameAgent | None = None,
    ) -> None:
        super().__init__()
        self._token = token
        self._streaming = streaming
        self._proxy = proxy
        self._stream_edit_interval = max(0, stream_edit_interval_ms) / 1000.0
        self._stream_edit_min_chars = max(1, stream_edit_min_chars)
        self._request_timeout = max(0, request_timeout_ms) / 1000.0
        self._app: Application | None = None
        # chat_id → {msg_id, text}, 用于流式增量编辑
        self._stream_buf: dict[str, dict] = {}
        if agent:
            self.bind_agent(agent)

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 Telegram 长轮询。"""
        logger.info(
            "telegram: preparing adapter (streaming={}, proxy={}, interval_ms={}, min_chars={}, request_timeout_ms={})",
            self._streaming,
            self._proxy or "<disabled>",
            int(self._stream_edit_interval * 1000),
            self._stream_edit_min_chars,
            int(self._request_timeout * 1000),
        )
        builder = Application.builder().token(self._token)
        if self._proxy:
            builder = builder.proxy(self._proxy).get_updates_proxy(self._proxy)
        self._app = builder.build()
        self._app.add_error_handler(self._on_error)
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self._on_message,
        ))
        self._app.add_handler(CommandHandler("start", self._on_start))
        logger.info("telegram: initializing application")
        await self._app.initialize()
        logger.info("telegram: starting application")
        await self._app.start()
        logger.info("telegram: starting long polling")
        await self._app.updater.start_polling()
        logger.info("telegram: long polling started")

    async def stop(self) -> None:
        """优雅关闭 Telegram 连接。"""
        if not self._app:
            return
        logger.info("telegram: stopping adapter")
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        self._app = None
        logger.info("telegram: adapter stopped")

    # ── 消息发送 ────────────────────────────────────────────────────────

    async def _request_with_timeout(self, chat_id: str, action: str, awaitable):
        """对 Telegram 请求加超时，避免单次 API 调用长时间阻塞。"""
        if self._request_timeout <= 0:
            return await awaitable
        try:
            return await asyncio.wait_for(awaitable, timeout=self._request_timeout)
        except TimeoutError:
            logger.warning(
                "telegram: {} timed out chat_id={} timeout_ms={}",
                action,
                chat_id,
                int(self._request_timeout * 1000),
            )
            return None

    async def send_text(self, chat_id: str, text: str) -> None:
        """发送完整文本消息。超出 4096 字符自动分块。"""
        if not self._app:
            logger.warning("telegram: send_text skipped because application is not ready")
            return
        rendered = render_markdown_to_telegram_html(text)
        logger.debug(
            "telegram: sending text chat_id={} chunks={} preview={}",
            chat_id,
            len(chunk_rendered_text(rendered)),
            _preview_text(text),
        )
        for chunk in chunk_rendered_text(rendered):
            await self._request_with_timeout(
                chat_id,
                "send_message",
                self._app.bot.send_message(
                    chat_id=int(chat_id),
                    text=chunk,
                    parse_mode=_TELEGRAM_PARSE_MODE,
                ),
            )

    async def send_delta(self, chat_id: str, delta: str, final: bool = False) -> None:
        """Telegram 流式增量发送。

        第 1 条 delta 发新消息，后续 delta 通过 ``edit_message_text``
        增量更新，参考 nanobot telegram channel 的 StreamBuf 模式。

        Parameters
        ----------
        chat_id:
            目标对话 ID。
        delta:
            本次增量文本（非完整文本）。
        final:
            是否为最终增量。
        """
        if not self._app:
            logger.warning("telegram: send_delta skipped because application is not ready")
            return

        if not final:
            if chat_id not in self._stream_buf:
                logger.debug(
                    "telegram: streaming first delta chat_id={} preview={}",
                    chat_id,
                    _preview_text(delta),
                )
                rendered_delta = render_markdown_to_telegram_html(delta)
                msg = await self._request_with_timeout(
                    chat_id,
                    "send_message",
                    self._app.bot.send_message(
                        chat_id=int(chat_id),
                        text=rendered_delta,
                        parse_mode=_TELEGRAM_PARSE_MODE,
                    ),
                )
                if msg is None:
                    return
                self._stream_buf[chat_id] = {"msg_id": msg.message_id, "text": delta}
            else:
                buf = self._stream_buf[chat_id]
                buf["text"] += delta
                elapsed = time.monotonic() - float(buf.get("last_edit_at", 0.0))
                pending_chars = len(buf["text"]) - len(str(buf.get("sent_text", "")))
                if elapsed < self._stream_edit_interval and pending_chars < self._stream_edit_min_chars:
                    logger.debug(
                        "telegram: streaming update deferred chat_id={} elapsed_ms={} pending_chars={} preview={}",
                        chat_id,
                        int(elapsed * 1000),
                        pending_chars,
                        _preview_text(buf["text"]),
                    )
                    return
                logger.debug(
                    "telegram: streaming delta update chat_id={} preview={}",
                    chat_id,
                    _preview_text(buf["text"]),
                )
                rendered_text = render_markdown_to_telegram_html(buf["text"])
                try:
                    await self._request_with_timeout(
                        chat_id,
                        "edit_message_text",
                        self._app.bot.edit_message_text(
                            chat_id=int(chat_id),
                            message_id=buf["msg_id"],
                            text=rendered_text,
                            parse_mode=_TELEGRAM_PARSE_MODE,
                        ),
                    )
                except RetryAfter as exc:
                    logger.warning(
                        "telegram: rate limited on delta edit chat_id={} retry_after={}s",
                        chat_id,
                        exc.retry_after,
                    )
                    return
                buf["sent_text"] = buf["text"]
                buf["last_edit_at"] = time.monotonic()
        else:
            buf = self._stream_buf.pop(chat_id, None)
            if buf:
                if buf.get("sent_text") == delta:
                    logger.debug(
                        "telegram: streaming final update skipped (unchanged) chat_id={} preview={}",
                        chat_id,
                        _preview_text(delta),
                    )
                    return
                logger.debug(
                    "telegram: streaming final update chat_id={} preview={}",
                    chat_id,
                    _preview_text(delta),
                )
                rendered_delta = render_markdown_to_telegram_html(delta)
                try:
                    await self._request_with_timeout(
                        chat_id,
                        "edit_message_text",
                        self._app.bot.edit_message_text(
                            chat_id=int(chat_id),
                            message_id=buf["msg_id"],
                            text=rendered_delta,
                            parse_mode=_TELEGRAM_PARSE_MODE,
                        ),
                    )
                except RetryAfter as exc:
                    logger.warning(
                        "telegram: rate limited on final edit chat_id={} retry_after={}s",
                        chat_id,
                        exc.retry_after,
                    )
                    return
                except BadRequest as exc:
                    if "Message is not modified" in str(exc):
                        logger.debug(
                            "telegram: final edit ignored because message was unchanged chat_id={}",
                            chat_id,
                        )
                        return
                    raise
            else:
                logger.debug(
                    "telegram: streaming final fallback to send_text chat_id={} preview={}",
                    chat_id,
                    _preview_text(delta),
                )
                await self.send_text(chat_id, delta)

    # ── 事件处理 ────────────────────────────────────────────────────────

    async def _on_message(self, update: Update, _context: object) -> None:
        """处理收到的文本消息。"""
        if not update.message or not update.message.text:
            return
        chat_id = str(update.effective_chat.id)
        user_id = str(update.effective_user.id) if update.effective_user else "0"
        text = update.message.text
        logger.info(
            "telegram: received message chat_id={} user_id={} text={}",
            chat_id,
            user_id,
            _preview_text(text),
        )
        try:
            reply = await self._handle_message(chat_id, user_id, text)
        except Exception:
            logger.exception(
                "telegram: handler failed chat_id={} user_id={} text={}",
                chat_id,
                user_id,
                _preview_text(text),
            )
            raise
        if reply is None:
            logger.warning(
                "telegram: message ignored chat_id={} user_id={} (agent missing or rejected)",
                chat_id,
                user_id,
            )
        else:
            logger.info(
                "telegram: replied chat_id={} user_id={} preview={}",
                chat_id,
                user_id,
                _preview_text(reply),
            )

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
