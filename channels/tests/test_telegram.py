"""TelegramAdapter 单元测试。

所有测试使用 pytest-mock 拦截 ``python-telegram-bot`` 的 SDK，
无需真实 Bot Token 和网络连接。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import BotCommand, InlineKeyboardMarkup
from telegram.error import BadRequest

from channels.telegram.adapter import TelegramAdapter, _StreamBuf
from channels.telegram.render import (
    chunk_rendered_text,
    render_markdown_to_telegram_html,
)
from channels.tests.conftest import FakeAgent, FakeErrorAgent
from rpg_core.agent.command import CommandDef


@pytest.fixture
def mock_app() -> MagicMock:
    """Mock ``Application.builder()`` 的完整链。"""
    builder = MagicMock()
    builder.token.return_value = builder
    builder.proxy.return_value = builder
    builder.get_updates_proxy.return_value = builder
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.set_my_commands = AsyncMock()
    builder.build.return_value = app
    return builder.build.return_value


@pytest.fixture
def adapter(mock_app: MagicMock) -> TelegramAdapter:
    """创建一个已注入 mock app 的 TelegramAdapter。"""
    a = TelegramAdapter(
        token="fake:token",
        streaming=True,
        workspace="data/tg_workspace",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        session_title="Telegram",
    )
    a._app = mock_app  # 注入 mock，避免真实网络连接
    return a


class TestTelegramAdapter:
    """TelegramAdapter 核心功能测试。"""

    async def test_get_session_id(self, adapter: TelegramAdapter):
        assert adapter.get_session_id("12345") == "tg_default"
        assert adapter.get_session_id("abc") == "tg_default"

    async def test_get_session_id_respects_pinned_session(self, adapter: TelegramAdapter):
        adapter._session_flow.pin_session("12345", "my_tel")
        assert adapter.get_session_id("12345") == "my_tel"

    async def test_default_streaming_flag(self):
        a = TelegramAdapter(token="fake:token", session_id="tg_default", workspace="data/tg")
        assert a._streaming is True  # 默认流式

        a2 = TelegramAdapter(token="fake:token", streaming=False, session_id="tg_default", workspace="data/tg")
        assert a2._streaming is False

    async def test_stream_throttle_defaults(self):
        a = TelegramAdapter(token="fake:token", session_id="tg_default", workspace="data/tg")
        assert a._stream_edit_interval == 0.8
        assert a._stream_edit_min_chars == 24
        assert a._request_timeout == 5.0

    async def test_proxy_is_stored(self):
        a = TelegramAdapter(token="fake:token", proxy="http://127.0.0.1:7890", session_id="tg_default", workspace="data/tg")
        assert a._proxy == "http://127.0.0.1:7890"

    async def test_on_message_routes_to_agent_client(self, adapter: TelegramAdapter):
        adapter._handle_message = AsyncMock(return_value="reply text")
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "hello"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        adapter._handle_message.assert_awaited_once_with("123", "456", "hello")

    async def test_on_message_handler_exception_sends_friendly_reply(self, adapter: TelegramAdapter):
        adapter._handle_message = AsyncMock(side_effect=RuntimeError("boom"))
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "hello"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        adapter.send_text.assert_awaited_once_with("123", "处理消息失败，请稍后重试。")

    async def test_on_command_routes_to_agent_client(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.execute_command = AsyncMock(
            return_value={"reply": "done", "handled": True},
        )
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/clear  "
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        agent.execute_command.assert_awaited_once()
        assert agent.execute_command.await_args.args[-1] == "/clear"
        adapter.send_text.assert_awaited_once_with("123", "done")

    async def test_on_command_sessions_shows_picker(self, adapter: TelegramAdapter, monkeypatch):
        agent = FakeAgent()
        agent.list_sessions = AsyncMock(return_value={"sessions": ["session_a", "session_b"]})
        adapter.bind_agent_client(agent)
        adapter._app.bot.send_message = AsyncMock()
        adapter._session_flow.pin_session("123", "session_b")
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/sessions"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        adapter._app.bot.send_message.assert_awaited_once()
        kwargs = adapter._app.bot.send_message.call_args.kwargs
        assert kwargs["chat_id"] == 123
        assert "会话列表 (2):" in kwargs["text"]
        assert "当前会话: session_b" in kwargs["text"]
        assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
        assert any("session_a" in button.text for row in kwargs["reply_markup"].inline_keyboard for button in row)
        assert any("新建会话" in button.text for row in kwargs["reply_markup"].inline_keyboard for button in row)

    async def test_session_picker_truncates_long_session_list(self, adapter: TelegramAdapter):
        sessions = [f"session_{idx}" for idx in range(25)]

        text = adapter._session_flow.render_session_picker_text(sessions, "session_1")
        markup = adapter._session_flow.build_session_picker(sessions, "session_1")

        assert "... 还有 5 个会话未展示" in text
        # 20 个可见会话 + 1 个新建会话按钮
        assert len(markup.inline_keyboard) == 21

    async def test_on_command_session_switch_without_args_shows_picker(self, adapter: TelegramAdapter, monkeypatch):
        agent = FakeAgent()
        agent.list_sessions = AsyncMock(return_value={"sessions": ["session_a", "session_b"]})
        adapter.bind_agent_client(agent)
        adapter._app.bot.send_message = AsyncMock()
        adapter._session_flow.pin_session("123", "session_b")
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/session_switch"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        adapter._app.bot.send_message.assert_awaited_once()
        kwargs = adapter._app.bot.send_message.call_args.kwargs
        assert "会话列表 (2):" in kwargs["text"]
        assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)

    async def test_on_command_normalizes_bot_mention(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.execute_command = AsyncMock(
            return_value={"reply": "done", "handled": True},
        )
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/compact@nanobot 10 5"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        agent.execute_command.assert_awaited_once()
        assert agent.execute_command.await_args.args[-1] == "/compact 10 5"
        adapter.send_text.assert_awaited_once_with("123", "done")

    async def test_on_command_normalizes_menu_alias(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.create_session = AsyncMock(
            return_value={"session_id": "generated_1", "title": "abc"},
        )
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/session_create abc"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        agent.create_session.assert_awaited_once_with("tg_workspace", 1, title="abc")
        adapter.send_text.assert_awaited_once_with("123", "[会话已创建: generated_1]")

    async def test_on_command_session_create_creates_immediately(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.create_session = AsyncMock(
            return_value={"session_id": "generated_1", "title": "Telegram"},
        )
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/session_create"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        assert not adapter._session_flow._pending_session_create  # noqa: SLF001
        agent.create_session.assert_awaited_once_with("tg_workspace", 1, title="Telegram")
        adapter.send_text.assert_awaited_once_with("123", "[会话已创建: generated_1]")

    async def test_on_command_unknown(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.execute_command = AsyncMock(return_value={"reply": "", "handled": False})
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/nope"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        adapter.send_text.assert_awaited_once_with("123", "未知命令: /nope")

    async def test_pending_session_create_consumes_plain_text(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.create_session = AsyncMock(
            return_value={"session_id": "generated_1", "title": "my title"},
        )
        adapter.bind_agent_client(agent)
        from channels.telegram.session_flow import _PendingSessionCreate
        import channels.telegram.session_flow as telegram_session_flow_module

        adapter._session_flow._pending_session_create["123"] = _PendingSessionCreate(
            started_at=telegram_session_flow_module.time.monotonic(),
        )
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "my title"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        agent.create_session.assert_awaited_once_with("tg_workspace", 1, title="my title")
        assert "123" not in adapter._session_flow._pending_session_create  # noqa: SLF001
        adapter.send_text.assert_awaited_once_with("123", "[会话已创建: generated_1]")

    async def test_pending_session_create_does_not_pin_new_session_by_default(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.create_session = AsyncMock(
            return_value={"session_id": "generated_1", "title": "my title"},
        )
        adapter.bind_agent_client(agent)
        adapter._session_flow.start_session_create_flow("123")
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "my title"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        assert adapter.get_session_id("123") == "tg_default"

    async def test_pending_session_create_can_pin_new_session_when_enabled(self, mock_app: MagicMock):
        adapter = TelegramAdapter(
            token="fake:token",
            streaming=True,
            auto_pin_created_session=True,
            workspace="data/tg_workspace",
            workspace_id="tg_workspace",
            story_id=1,
            session_id="tg_default",
            session_title="Telegram",
        )
        adapter._app = mock_app
        agent = FakeAgent()
        agent.create_session = AsyncMock(
            return_value={"session_id": "generated_1", "title": "my title"},
        )
        adapter.bind_agent_client(agent)
        adapter._session_flow.start_session_create_flow("123")
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "my title"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        assert adapter.get_session_id("123") == "generated_1"

    async def test_pending_session_create_timeout_consumes_once(self, adapter: TelegramAdapter):
        from channels.telegram.session_flow import _PendingSessionCreate
        import channels.telegram.session_flow as telegram_session_flow_module

        adapter._session_flow._pending_session_create["123"] = _PendingSessionCreate(  # noqa: SLF001
            started_at=telegram_session_flow_module.time.monotonic() - 301,
        )
        adapter._handle_message = AsyncMock()
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "my_tel"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        adapter._handle_message.assert_not_called()
        adapter.send_text.assert_awaited_once()
        assert "会话创建已超时" in adapter.send_text.call_args.args[1]

    async def test_pending_session_create_accepts_title_text(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.create_session = AsyncMock(
            return_value={"session_id": "generated_1", "title": "我想要一个新会话"},
        )
        adapter.bind_agent_client(agent)
        from channels.telegram.session_flow import _PendingSessionCreate
        import channels.telegram.session_flow as telegram_session_flow_module

        adapter._session_flow._pending_session_create["123"] = _PendingSessionCreate(
            started_at=telegram_session_flow_module.time.monotonic(),
        )
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "我想要一个新会话"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        assert "123" not in adapter._session_flow._pending_session_create  # noqa: SLF001
        agent.create_session.assert_awaited_once()
        adapter.send_text.assert_awaited_once_with("123", "[会话已创建: generated_1]")

    async def test_pending_session_create_canceled_by_temporary_command(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        adapter.bind_agent_client(agent)
        adapter._session_flow.start_session_create_flow("123")
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/cancel"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        assert "123" not in adapter._session_flow._pending_session_create  # noqa: SLF001
        adapter.send_text.assert_awaited_once_with("123", "已取消创建会话。")

    async def test_on_command_start(self, adapter: TelegramAdapter):
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/start"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        adapter.send_text.assert_awaited_once()
        assert "欢迎使用 RPG World" in adapter.send_text.call_args.args[1]

    async def test_on_command_session_switch_pins_chat_session(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.execute_command = AsyncMock(
            return_value={"reply": "[已切换到会话: my_tel]", "handled": True, "active_session": "my_tel"},
        )
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/session_switch my_tel"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        assert adapter.get_session_id("123") == "my_tel"
        adapter.send_text.assert_awaited_once_with("123", "[已切换到会话: my_tel]")

    async def test_session_id_validation_has_length_limit(self):
        from rpg_core.session import SessionManager

        assert SessionManager.is_valid_session_id("a" * 64)
        assert not SessionManager.is_valid_session_id("a" * 65)
        with pytest.raises(ValueError) as exc_info:
            SessionManager.validate_session_id("a" * 65)
        assert "at most 64 characters" in str(exc_info.value)

    async def test_pinned_session_is_used_for_followup_messages(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        adapter.bind_agent_client(agent)
        adapter._session_flow.pin_session("123", "my_tel")
        adapter._app.bot.send_message = AsyncMock()
        adapter._app.bot.edit_message_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "hello"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        assert agent.calls[-1] == (
            "stream",
            ("my_tel", "hello"),
        )

    async def test_start_configures_proxy_and_handlers(self, monkeypatch):
        builder = MagicMock()
        builder.token.return_value = builder
        builder.proxy.return_value = builder
        builder.get_updates_proxy.return_value = builder
        app = MagicMock()
        app.bot = MagicMock()
        app.bot.set_my_commands = AsyncMock()
        app.initialize = AsyncMock()
        app.start = AsyncMock()
        app.shutdown = AsyncMock()
        app.updater = MagicMock()
        app.updater.start_polling = AsyncMock()
        app.updater.stop = AsyncMock()
        app.add_handler = MagicMock()
        app.add_error_handler = MagicMock()
        builder.build.return_value = app

        monkeypatch.setattr(
            "channels.telegram.adapter.Application.builder",
            MagicMock(return_value=builder),
        )

        adapter = TelegramAdapter(
            token="fake:token",
            proxy="http://127.0.0.1:7890",
            workspace="data/tg_workspace",
            workspace_id="tg_workspace",
            story_id=1,
            session_id="tg_default",
            session_title="Telegram",
        )
        agent = FakeAgent()
        agent._commands = [
            *agent._commands,
            CommandDef(name="/session_create", description="create", detail="create session"),
            CommandDef(name="/session_switch", description="switch", detail="switch session"),
            CommandDef(name="/memory_reindex", description="reindex", detail="reindex memory"),
        ]
        agent._ensure_initialized = AsyncMock()
        adapter.bind_agent_client(agent)
        await adapter.start()

        builder.token.assert_called_once_with("fake:token")
        builder.proxy.assert_called_once_with("http://127.0.0.1:7890")
        builder.get_updates_proxy.assert_called_once_with("http://127.0.0.1:7890")
        app.add_error_handler.assert_called_once()
        assert app.add_handler.call_count == 3
        app.bot.set_my_commands.assert_awaited_once()
        commands = app.bot.set_my_commands.call_args.args[0]
        assert isinstance(commands[0], BotCommand)
        assert commands[0].command == "start"
        assert any(cmd.command == "help" for cmd in commands)
        assert any(cmd.command == "clear" for cmd in commands)
        assert any(cmd.command == "session_create" for cmd in commands)
        assert any(cmd.command == "session_switch" for cmd in commands)
        assert any(cmd.command == "memory_reindex" for cmd in commands)
        app.initialize.assert_awaited_once()
        app.start.assert_awaited_once()
        app.updater.start_polling.assert_awaited_once()

    async def test_start_rejects_empty_token(self):
        adapter = TelegramAdapter(token="")

        with pytest.raises(ValueError):
            await adapter.start()

    async def test_configure_bot_commands_filters_invalid_and_truncates(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent._commands = [
            CommandDef(name="/valid_cmd", description="x" * 300, detail=""),
            CommandDef(name="/bad-name", description="bad", detail=""),
        ]
        adapter.bind_agent_client(agent)
        adapter._app.bot.set_my_commands = AsyncMock()

        await adapter._configure_bot_commands()

        commands = adapter._app.bot.set_my_commands.call_args.args[0]
        command_names = [cmd.command for cmd in commands]
        assert "valid_cmd" in command_names
        assert "bad-name" not in command_names
        valid = next(cmd for cmd in commands if cmd.command == "valid_cmd")
        assert len(valid.description) == 256

    async def test_send_text(self, adapter: TelegramAdapter):
        """send_text 应调 bot.send_message 发送完整文本。"""
        adapter._app.bot.send_message = AsyncMock()

        await adapter.send_text("123", "hello world")

        adapter._app.bot.send_message.assert_called_once_with(
            chat_id=123,
            text="hello world",
            parse_mode="HTML",
        )

    async def test_send_text_bad_request_is_swallowed(self, adapter: TelegramAdapter):
        adapter._app.bot.send_message = AsyncMock(side_effect=BadRequest("broken"))

        await adapter.send_text("123", "hello world")

        adapter._app.bot.send_message.assert_called_once()

    async def test_send_text_escapes_markdown(self, adapter: TelegramAdapter):
        adapter._app.bot.send_message = AsyncMock()

        await adapter.send_text("123", "hello_world")

        adapter._app.bot.send_message.assert_called_once_with(
            chat_id=123,
            text="hello_world",
            parse_mode="HTML",
        )

    async def test_render_markdown_to_html(self):
        text = (
            "你低头打量了一下自己——身为一名勇猛的骑士，你的装备如下：\n\n"
            "---\n\n"
            "**🛡️ Bob 当前装备**\n\n"
            "| 部位 | 物品 | 状态 |\n"
            "|------|------|------|\n"
            "| **武器** | 双手重剑「铁砧」 | 剑刃有些磨损，但依然锋利 |\n"
        )

        rendered = render_markdown_to_telegram_html(text)

        assert "<b>🛡️ Bob 当前装备</b>" in rendered
        assert "• <b>武器</b>: 双手重剑「铁砧」 — 剑刃有些磨损，但依然锋利" in rendered

    async def test_render_lists_with_indentation(self):
        text = (
            "- 主线任务\n"
            "  - 找到祭坛\n"
            "  - 解开封印\n"
            "1. 先侦察\n"
            "2. 再推进\n"
        )

        rendered = render_markdown_to_telegram_html(text)

        assert "• 主线任务" in rendered
        assert "\u00a0\u00a0• 找到祭坛" in rendered
        assert "\u00a0\u00a0• 解开封印" in rendered
        assert "1. 先侦察" in rendered
        assert "2. 再推进" in rendered

    async def test_render_headings_links_and_tasks(self):
        text = (
            "# 任务日志\n"
            "## 当前目标\n"
            "- [ ] 前往祭坛\n"
            "- [x] 与守卫交谈\n"
            "参考 [地图](https://example.com/map) 或 `help`。\n"
        )

        rendered = render_markdown_to_telegram_html(text)

        assert "<b>任务日志</b>" in rendered
        assert "<b>当前目标</b>" in rendered
        assert "☐ 前往祭坛" in rendered
        assert "☑ 与守卫交谈" in rendered
        assert '<a href="https://example.com/map">地图</a>' in rendered
        assert "<code>help</code>" in rendered

    async def test_render_escapes_rp_output_xml_tags(self):
        text = '<rp-narration>风声停了。</rp-narration>\n<rp-character name="Alice">走吧。</rp-character>'

        rendered = render_markdown_to_telegram_html(text)

        assert "&lt;rp-narration&gt;风声停了。&lt;/rp-narration&gt;" in rendered
        assert "&lt;rp-character name=\"Alice\"&gt;走吧。&lt;/rp-character&gt;" in rendered

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
        assert adapter._stream_buf["123"].msg_id == 42
        assert adapter._stream_buf["123"].text == "Hello "

    async def test_send_delta_subsequent(self, adapter: TelegramAdapter):
        """后续 delta 应编辑已有消息。"""
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="Hello ",
            sent_text="Hello ",
            last_edit_at=0.0,
        )
        adapter._app.bot.edit_message_text = AsyncMock()

        await adapter.send_delta("123", "World", final=False)

        adapter._app.bot.edit_message_text.assert_called_once_with(
            chat_id=123,
            message_id=42,
            text="Hello World",
            parse_mode="HTML",
        )
        assert adapter._stream_buf["123"].text == "Hello World"

    async def test_send_delta_subsequent_edit_failure_keeps_pending_text(self, adapter: TelegramAdapter):
        """中间编辑失败后不应把未发送文本标记为已发送。"""
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="Hello ",
            sent_text="Hello ",
            last_edit_at=0.0,
        )
        adapter._app.bot.edit_message_text = AsyncMock(return_value=None)

        await adapter.send_delta("123", "World", final=False)

        assert adapter._stream_buf["123"].text == "Hello World"
        assert adapter._stream_buf["123"].sent_text == "Hello "
        assert adapter._stream_buf["123"].last_edit_at > 0.0

    async def test_send_delta_first_send_failure_keeps_single_pending_buffer(self, adapter: TelegramAdapter):
        """首次发送失败后，后续 delta 应复用同一 pending buffer 再发送合并文本。"""
        adapter._app.bot.send_message = AsyncMock(side_effect=[None, MagicMock(message_id=42)])

        await adapter.send_delta("123", "Hello ", final=False)
        await adapter.send_delta("123", "World", final=False)

        assert adapter._app.bot.send_message.await_count == 2
        second_call = adapter._app.bot.send_message.await_args_list[1]
        assert second_call.kwargs["text"] == "Hello World"
        assert adapter._stream_buf["123"].msg_id == 42
        assert adapter._stream_buf["123"].text == "Hello World"
        assert adapter._stream_buf["123"].sent_text == "Hello World"

    async def test_stream_error_clears_buffer_and_notifies_user(self, adapter: TelegramAdapter):
        """流式 ERROR 后应清理 buffer，避免下一条消息复用失效状态。"""
        agent = FakeErrorAgent()
        adapter.bind_agent_client(agent)
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="stale",
            sent_text="stale",
            last_edit_at=0.0,
        )
        adapter.send_text = AsyncMock()

        result = await adapter._stream_and_send("123", "hi")

        assert result.text == ""
        assert "123" not in adapter._stream_buf
        adapter.send_text.assert_awaited_once_with("123", "处理消息失败，请稍后重试。")

    async def test_send_delta_subsequent_throttled(self, adapter: TelegramAdapter):
        """未到节流阈值时不应立即编辑消息。"""
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="Hello ",
            sent_text="Hello ",
            last_edit_at=1000.0,
        )
        adapter._app.bot.edit_message_text = AsyncMock()

        import channels.telegram.adapter as telegram_adapter_module

        original_monotonic = telegram_adapter_module.time.monotonic
        telegram_adapter_module.time.monotonic = lambda: 1000.1
        try:
            await adapter.send_delta("123", "World", final=False)
        finally:
            telegram_adapter_module.time.monotonic = original_monotonic

        adapter._app.bot.edit_message_text.assert_not_called()
        assert adapter._stream_buf["123"].text == "Hello World"

    async def test_send_delta_final_with_buffer(self, adapter: TelegramAdapter):
        """final delta 应编辑最终文本并清理 buffer。"""
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="Hello ",
            sent_text="Hello ",
            last_edit_at=0.0,
        )
        adapter._app.bot.edit_message_text = AsyncMock()

        await adapter.send_delta("123", "Hello World!", final=True)

        adapter._app.bot.edit_message_text.assert_called_once_with(
            chat_id=123,
            message_id=42,
            text="Hello World!",
            parse_mode="HTML",
        )
        assert "123" not in adapter._stream_buf  # buffer 已清理

    async def test_send_delta_final_edit_failure_falls_back_to_send_text(self, adapter: TelegramAdapter):
        """final 编辑失败时应回退为 send_text，避免用户收不到回复。"""
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="Hello ",
            sent_text="Hello ",
            last_edit_at=0.0,
        )
        adapter._app.bot.edit_message_text = AsyncMock(return_value=None)
        adapter._app.bot.send_message = AsyncMock()

        await adapter.send_delta("123", "Hello World!", final=True)

        adapter._app.bot.edit_message_text.assert_called_once()
        adapter._app.bot.send_message.assert_called_once_with(
            chat_id=123, text="Hello World!", parse_mode="HTML",
        )
        assert "123" not in adapter._stream_buf

    async def test_send_delta_final_unchanged_is_noop(self, adapter: TelegramAdapter):
        """final delta 与当前缓冲内容完全一致时应直接跳过。"""
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="Hello World!",
            sent_text="Hello World!",
            last_edit_at=0.0,
        )
        adapter._app.bot.edit_message_text = AsyncMock()

        await adapter.send_delta("123", "Hello World!", final=True)

        adapter._app.bot.edit_message_text.assert_not_called()
        assert "123" not in adapter._stream_buf

    async def test_send_delta_final_flushes_deferred_updates(self, adapter: TelegramAdapter):
        """前面的流式更新都被节流时，final 仍应补发最终内容。"""
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="Hello World!",
            sent_text="Hello ",
            last_edit_at=1000.0,
        )
        adapter._app.bot.edit_message_text = AsyncMock()

        await adapter.send_delta("123", "Hello World!", final=True)

        adapter._app.bot.edit_message_text.assert_called_once_with(
            chat_id=123,
            message_id=42,
            text="Hello World!",
            parse_mode="HTML",
        )
        assert "123" not in adapter._stream_buf

    async def test_send_delta_final_without_buffer(self, adapter: TelegramAdapter):
        """无 buffer 时的 final delta 应降级为 send_text。"""
        adapter._app.bot.send_message = AsyncMock()

        await adapter.send_delta("123", "Direct text", final=True)

        adapter._app.bot.send_message.assert_called_once_with(
            chat_id=123, text="Direct text", parse_mode="HTML",
        )

    async def test_send_delta_final_long_text_falls_back_to_chunks(self, adapter: TelegramAdapter):
        adapter._stream_buf["123"] = _StreamBuf(
            msg_id=42,
            text="x",
            sent_text="x",
            last_edit_at=0.0,
        )
        adapter._app.bot.edit_message_text = AsyncMock()
        adapter._app.bot.send_message = AsyncMock()

        await adapter.send_delta("123", "x" * 5000, final=True)

        adapter._app.bot.edit_message_text.assert_not_called()
        assert adapter._app.bot.send_message.call_count == 2

    async def test_name_is_instance_specific(self):
        assert TelegramAdapter(token="fake:token").name == "telegram_default"
        assert TelegramAdapter(token="fake:token", bot_name="main").name == "telegram_main"

    async def test_bind_agent_client_client(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        adapter.bind_agent_client(agent)
        assert adapter._agent_client is agent

    async def test_no_app_send_text_noop(self):
        """_app 为 None 时 send_text 应静默跳过。"""
        a = TelegramAdapter(token="fake:token")
        assert a._app is None
        # 不应抛异常
        await a.send_text("123", "hello")


class TestChunkText:
    def test_short_text(self):
        assert chunk_rendered_text("hello") == ["hello"]

    def test_exact_chunk(self):
        text = "a" * 4096
        assert chunk_rendered_text(text) == [text]

    def test_long_text(self):
        text = "a" * 5000
        chunks = chunk_rendered_text(text)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4096
        assert len(chunks[1]) == 5000 - 4096

    def test_empty_text(self):
        assert chunk_rendered_text("") == []

    def test_linewise_chunking(self):
        text = "第一行\n第二行\n第三行\n"
        chunks = chunk_rendered_text(text, max_len=5)
        assert chunks == ["第一行\n", "第二行\n", "第三行\n"]
