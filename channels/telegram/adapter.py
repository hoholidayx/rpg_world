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

from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from rpg_world.channels.base import ChannelAdapter

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.agent import RPGGameAgent

_TELEGRAM_MAX_LEN = 4096


def _chunk_text(text: str, max_len: int = _TELEGRAM_MAX_LEN) -> list[str]:
    """将长文本按 *max_len* 切分为多个片段。"""
    return [text[i : i + max_len] for i in range(0, len(text), max_len)]


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
        agent: RPGGameAgent | None = None,
    ) -> None:
        super().__init__()
        self._token = token
        self._streaming = streaming
        self._app: Application | None = None
        # chat_id → {msg_id, text}, 用于流式增量编辑
        self._stream_buf: dict[str, dict] = {}
        if agent:
            self.bind_agent(agent)

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 Telegram 长轮询。"""
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self._on_message,
        ))
        self._app.add_handler(CommandHandler("start", self._on_start))
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        """优雅关闭 Telegram 连接。"""
        if not self._app:
            return
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        self._app = None

    # ── 消息发送 ────────────────────────────────────────────────────────

    async def send_text(self, chat_id: str, text: str) -> None:
        """发送完整文本消息。超出 4096 字符自动分块。"""
        if not self._app:
            return
        for chunk in _chunk_text(text):
            await self._app.bot.send_message(
                chat_id=int(chat_id),
                text=chunk,
                parse_mode="HTML",
            )

    async def send_delta(self, chat_id: str, delta: str, final: bool = False) -> None:
        """Telegram 流式增量发送。

        第 1 条 delta 发新消息，后续 delta 通过 ``edit_message_text``
        增量更新，参考 nanobot telegram channel 的 \_StreamBuf 模式。

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
            return

        if not final:
            if chat_id not in self._stream_buf:
                msg = await self._app.bot.send_message(
                    chat_id=int(chat_id),
                    text=delta,
                    parse_mode="HTML",
                )
                self._stream_buf[chat_id] = {"msg_id": msg.message_id, "text": delta}
            else:
                buf = self._stream_buf[chat_id]
                buf["text"] += delta
                await self._app.bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=buf["msg_id"],
                    text=buf["text"],
                    parse_mode="HTML",
                )
        else:
            buf = self._stream_buf.pop(chat_id, None)
            if buf:
                await self._app.bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=buf["msg_id"],
                    text=delta,
                    parse_mode="HTML",
                )
            else:
                await self.send_text(chat_id, delta)

    # ── 事件处理 ────────────────────────────────────────────────────────

    async def _on_message(self, update: Update, _context: object) -> None:
        """处理收到的文本消息。"""
        if not update.message or not update.message.text:
            return
        chat_id = str(update.effective_chat.id)
        user_id = str(update.effective_user.id) if update.effective_user else "0"
        text = update.message.text
        await self._handle_message(chat_id, user_id, text)

    async def _on_start(self, update: Update, _context: object) -> None:
        """处理 /start 命令。"""
        if not update.message:
            return
        chat_id = str(update.effective_chat.id)
        await self.send_text(chat_id, "欢迎使用 RPG World！发送消息开始冒险。")
