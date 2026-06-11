"""TelegramAdapter 单元测试。

所有测试使用 pytest-mock 拦截 ``python-telegram-bot`` 的 SDK，
无需真实 Bot Token 和网络连接。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rpg_world.channels.telegram.adapter import TelegramAdapter, _chunk_text
from rpg_world.channels.tests.conftest import FakeAgent, FakeBot


@pytest.fixture
def mock_app() -> MagicMock:
    """Mock ``Application.builder()`` 的完整链。"""
    builder = MagicMock()
    builder.token.return_value = builder
    builder.build.return_value = MagicMock()
    return builder.build.return_value


@pytest.fixture
def adapter(mock_app: MagicMock) -> TelegramAdapter:
    """创建一个已注入 mock app 的 TelegramAdapter。"""
    a = TelegramAdapter(token="fake:token", streaming=True)
    a._app = mock_app  # 注入 mock，避免真实网络连接
    return a


class TestTelegramAdapter:
    """TelegramAdapter 核心功能测试。"""

    async def test_get_session_id(self, adapter: TelegramAdapter):
        assert adapter.get_session_id("12345") == "telegram_12345"
        assert adapter.get_session_id("abc") == "telegram_abc"

    async def test_default_streaming_flag(self):
        a = TelegramAdapter(token="fake:token")
        assert a._streaming is True  # 默认流式

        a2 = TelegramAdapter(token="fake:token", streaming=False)
        assert a2._streaming is False

    async def test_send_text(self, adapter: TelegramAdapter):
        """send_text 应调 bot.send_message 发送完整文本。"""
        adapter._app.bot.send_message = AsyncMock()

        await adapter.send_text("123", "hello world")

        adapter._app.bot.send_message.assert_called_once_with(
            chat_id=123,
            text="hello world",
            parse_mode="HTML",
        )

    async def test_send_text_long(self, adapter: TelegramAdapter):
        """超过 4096 字符的文本应自动分块发送。"""
        adapter._app.bot.send_message = AsyncMock()

        long_text = "x" * 5000
        await adapter.send_text("123", long_text)

        assert adapter._app.bot.send_message.call_count == 2
        args1 = adapter._app.bot.send_message.call_args_list[0][1]
        args2 = adapter._app.bot.send_message.call_args_list[1][1]
        assert args1["chat_id"] == 123
        assert args2["chat_id"] == 123
        assert len(args1["text"]) == 4096
        assert len(args2["text"]) == 5000 - 4096

    async def test_send_delta_first(self, adapter: TelegramAdapter):
        """第 1 条 delta 应发新消息并记录到 buffer。"""
        fake_msg = MagicMock()
        fake_msg.message_id = 42
        adapter._app.bot.send_message = AsyncMock(return_value=fake_msg)

        await adapter.send_delta("123", "Hello ", final=False)

        adapter._app.bot.send_message.assert_called_once_with(
            chat_id=123, text="Hello ", parse_mode="HTML",
        )
        assert "123" in adapter._stream_buf
        assert adapter._stream_buf["123"]["msg_id"] == 42
        assert adapter._stream_buf["123"]["text"] == "Hello "

    async def test_send_delta_subsequent(self, adapter: TelegramAdapter):
        """后续 delta 应编辑已有消息。"""
        adapter._stream_buf["123"] = {"msg_id": 42, "text": "Hello "}
        adapter._app.bot.edit_message_text = AsyncMock()

        await adapter.send_delta("123", "World", final=False)

        adapter._app.bot.edit_message_text.assert_called_once_with(
            chat_id=123,
            message_id=42,
            text="Hello World",
            parse_mode="HTML",
        )
        assert adapter._stream_buf["123"]["text"] == "Hello World"

    async def test_send_delta_final_with_buffer(self, adapter: TelegramAdapter):
        """final delta 应编辑最终文本并清理 buffer。"""
        adapter._stream_buf["123"] = {"msg_id": 42, "text": "Hello "}
        adapter._app.bot.edit_message_text = AsyncMock()

        await adapter.send_delta("123", "Hello World!", final=True)

        adapter._app.bot.edit_message_text.assert_called_once_with(
            chat_id=123,
            message_id=42,
            text="Hello World!",
            parse_mode="HTML",
        )
        assert "123" not in adapter._stream_buf  # buffer 已清理

    async def test_send_delta_final_without_buffer(self, adapter: TelegramAdapter):
        """无 buffer 时的 final delta 应降级为 send_text。"""
        adapter._app.bot.send_message = AsyncMock()

        await adapter.send_delta("123", "Direct text", final=True)

        adapter._app.bot.send_message.assert_called_once_with(
            chat_id=123, text="Direct text", parse_mode="HTML",
        )

    async def test_name_constant(self):
        assert TelegramAdapter.name == "telegram"

    async def test_bind_agent(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        adapter.bind_agent(agent)
        assert adapter._agent is agent

    async def test_no_app_send_text_noop(self):
        """_app 为 None 时 send_text 应静默跳过。"""
        a = TelegramAdapter(token="fake:token")
        assert a._app is None
        # 不应抛异常
        await a.send_text("123", "hello")


class TestChunkText:
    def test_short_text(self):
        assert _chunk_text("hello") == ["hello"]

    def test_exact_chunk(self):
        text = "a" * 4096
        assert _chunk_text(text) == [text]

    def test_long_text(self):
        text = "a" * 5000
        chunks = _chunk_text(text)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4096
        assert len(chunks[1]) == 5000 - 4096

    def test_empty_text(self):
        assert _chunk_text("") == []
