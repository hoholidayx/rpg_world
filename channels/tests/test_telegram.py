"""TelegramAdapter 单元测试。

所有测试使用 pytest-mock 拦截 ``python-telegram-bot`` 的 SDK，
无需真实 Bot Token 和网络连接。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import BotCommand, InlineKeyboardMarkup
from telegram.error import BadRequest

from channels.telegram.adapter import TelegramAdapter
from channels.telegram.render import (
    chunk_rendered_text,
    project_rp_text,
    render_markdown_to_telegram_html,
)
from channels.tests.conftest import FakeAgent
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind
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
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    app.bot.edit_message_text = AsyncMock(return_value=True)
    app.bot.edit_message_reply_markup = AsyncMock(return_value=True)
    app.bot.delete_message = AsyncMock(return_value=True)
    app.updater = MagicMock()
    app.updater.stop = AsyncMock()
    app.stop = AsyncMock()
    app.shutdown = AsyncMock()
    app.test_tasks = []

    def create_task(coroutine, **_kwargs):  # noqa: ANN001
        task = asyncio.create_task(coroutine)
        app.test_tasks.append(task)
        return task

    app.create_task = MagicMock(side_effect=create_task)
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


async def _drain_tasks(app: MagicMock) -> None:
    tasks = list(app.test_tasks)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _message_update(chat_id: int, text: str, *, user_id: int = 456) -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.effective_chat.id = chat_id
    update.effective_user.id = user_id
    return update


def _callback_update(chat_id: int, callback_data: str) -> MagicMock:
    update = MagicMock()
    query = MagicMock()
    query.data = callback_data
    query.message = MagicMock()
    query.message.chat.id = chat_id
    query.answer = AsyncMock()
    update.callback_query = query
    return update


class _BlockingAgent(FakeAgent):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(
        self,
        *args: str,
        request_id: str | None = None,
        **_kwargs: object,
    ):
        recorded_args = tuple(args) + ((request_id,) if request_id is not None else ())
        self.calls.append(("stream", recorded_args))
        self.started.set()
        await self.release.wait()
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content="done")


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
        agent = FakeAgent()
        adapter.bind_agent_client(agent)
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "hello"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())
        await _drain_tasks(adapter._app)

        assert agent.calls[-1][0] == "stream"
        assert agent.calls[-1][1][:2] == ("tg_default", "hello")
        assert str(agent.calls[-1][1][2]).startswith("tg_")

    async def test_on_message_handler_exception_sends_friendly_reply(self, adapter: TelegramAdapter):
        adapter.bind_agent_client(FakeAgent())
        adapter.send_text = AsyncMock()
        adapter._app.create_task = MagicMock(side_effect=RuntimeError("boom"))
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "hello"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_message(update, object())

        adapter.send_text.assert_awaited_once_with("123", "处理消息失败，请稍后重试。")

    async def test_on_message_returns_while_generation_is_running_and_rejects_same_chat(
        self,
        adapter: TelegramAdapter,
    ):
        agent = _BlockingAgent()
        adapter.bind_agent_client(agent)

        await adapter._on_message(_message_update(123, "first"), object())

        assert adapter._app.create_task.call_count == 1
        assert adapter._turn_flow.busy_reason("123", "tg_default") is not None
        await agent.started.wait()

        await adapter._on_message(_message_update(123, "second"), object())

        assert len([call for call in agent.calls if call[0] == "stream"]) == 1
        assert any(
            call.kwargs.get("text") == "当前消息仍在生成，请等待完成后再发送。"
            for call in adapter._app.bot.send_message.await_args_list
        )

        agent.release.set()
        await _drain_tasks(adapter._app)
        assert adapter._turn_flow.busy_reason("123", "tg_default") is None

    async def test_generation_rejects_other_chat_using_same_session(
        self,
        adapter: TelegramAdapter,
    ):
        agent = _BlockingAgent()
        adapter.bind_agent_client(agent)

        await adapter._on_message(_message_update(123, "first"), object())
        await agent.started.wait()
        await adapter._on_message(_message_update(999, "second"), object())

        assert len([call for call in agent.calls if call[0] == "stream"]) == 1
        assert any(
            call.kwargs.get("chat_id") == 999
            and call.kwargs.get("text") == "当前会话正在处理另一条消息，请稍后再试。"
            for call in adapter._app.bot.send_message.await_args_list
        )

        agent.release.set()
        await _drain_tasks(adapter._app)

    async def test_different_chats_on_different_sessions_can_generate_concurrently(
        self,
        adapter: TelegramAdapter,
    ):
        agent = _BlockingAgent()
        adapter.bind_agent_client(agent)
        adapter._session_flow.pin_session("999", "other_session")

        await adapter._on_message(_message_update(123, "first"), object())
        await adapter._on_message(_message_update(999, "second"), object())
        for _ in range(5):
            if len([call for call in agent.calls if call[0] == "stream"]) == 2:
                break
            await asyncio.sleep(0)

        stream_calls = [call for call in agent.calls if call[0] == "stream"]
        assert len(stream_calls) == 2
        assert {call[1][0] for call in stream_calls} == {"tg_default", "other_session"}

        agent.release.set()
        await _drain_tasks(adapter._app)

    async def test_commands_are_rejected_while_session_is_generating(
        self,
        adapter: TelegramAdapter,
    ):
        agent = _BlockingAgent()
        agent.execute_command = AsyncMock(return_value={"reply": "done", "handled": True})
        adapter.bind_agent_client(agent)

        await adapter._on_message(_message_update(123, "first"), object())
        await adapter._on_command(_message_update(123, "/clear"), object())

        agent.execute_command.assert_not_awaited()
        assert any(
            call.kwargs.get("text") == "当前会话正在生成，请完成后再执行命令。"
            for call in adapter._app.bot.send_message.await_args_list
        )

        agent.release.set()
        await _drain_tasks(adapter._app)

    async def test_busy_callback_is_not_claimed_and_can_be_retried_after_done(
        self,
        adapter: TelegramAdapter,
    ):
        agent = _BlockingAgent()
        adapter.bind_agent_client(agent)
        markup = adapter._session_flow.build_session_picker(
            "123",
            [
                {"session_id": "tg_default", "title": "Telegram"},
                {"session_id": "session_b", "title": "Session B"},
            ],
            "tg_default",
        )
        callback_data = markup.inline_keyboard[1][0].callback_data
        assert callback_data is not None

        await adapter._on_message(_message_update(123, "first"), object())
        busy_update = _callback_update(123, callback_data)
        await adapter._on_callback_query(busy_update, object())

        busy_update.callback_query.answer.assert_awaited_once_with(
            "当前会话正在生成，请完成后再操作。",
        )

        agent.release.set()
        await _drain_tasks(adapter._app)
        agent.execute_command = AsyncMock(
            return_value={
                "reply": "[已切换到会话: session_b]",
                "handled": True,
                "active_session": "session_b",
            },
        )
        retry_update = _callback_update(123, callback_data)
        await adapter._on_callback_query(retry_update, object())

        agent.execute_command.assert_awaited_once_with(
            "tg_default",
            "/session_switch session_b",
        )
        assert adapter.get_session_id("123") == "session_b"

    async def test_invalid_and_legacy_callbacks_show_expired_alert(self, adapter: TelegramAdapter):
        for callback_data in ("tg:a:missing", "tg_sess:legacy"):
            update = _callback_update(123, callback_data)

            await adapter._on_callback_query(update, object())

            update.callback_query.answer.assert_awaited_once_with(
                "该菜单已失效，请重新打开。",
                show_alert=True,
            )

    async def test_on_command_routes_to_agent_client(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.execute_command = AsyncMock(
            return_value={
                "reply": "当前会话已重置。\n\n新的开场白",
                "handled": True,
            },
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
        adapter.send_text.assert_awaited_once_with(
            "123",
            "当前会话已重置。\n\n新的开场白",
        )

    async def test_on_command_sessions_shows_picker(self, adapter: TelegramAdapter, monkeypatch):
        agent = FakeAgent()
        agent.list_sessions = AsyncMock(return_value={"sessions": [
            {"session_id": "session_a", "title": "Alpha"},
            {"session_id": "session_b", "title": "Beta"},
        ]})
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
        assert "Beta · session_b （当前）" in kwargs["text"]
        assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
        assert any("Alpha" in button.text for row in kwargs["reply_markup"].inline_keyboard for button in row)
        assert any("新建并进入" in button.text for row in kwargs["reply_markup"].inline_keyboard for button in row)

    async def test_session_picker_truncates_long_session_list(self, adapter: TelegramAdapter):
        sessions = [
            {"session_id": f"session_{idx}", "title": f"Session {idx}"}
            for idx in range(25)
        ]

        text = adapter._session_flow.render_session_picker_text(sessions, "session_1")
        markup = adapter._session_flow.build_session_picker("123", sessions, "session_1")

        assert "... 还有 5 个会话未展示" in text
        # 20 个可见会话 + 1 个新建会话按钮
        assert len(markup.inline_keyboard) == 21

    async def test_on_command_session_switch_without_args_shows_picker(self, adapter: TelegramAdapter, monkeypatch):
        agent = FakeAgent()
        agent.list_sessions = AsyncMock(return_value={"sessions": [
            {"session_id": "session_a", "title": "Alpha"},
            {"session_id": "session_b", "title": "Beta"},
        ]})
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
        assert adapter.get_session_id("123") == "generated_1"
        adapter.send_text.assert_awaited_once_with("123", "已新建并进入会话：abc · generated_1")

    async def test_on_command_session_create_prompts_for_title(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.create_session = AsyncMock()
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/session_create"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        assert "123" in adapter._session_flow._pending_session_create  # noqa: SLF001
        agent.create_session.assert_not_awaited()
        assert "请输入新会话标题" in adapter.send_text.call_args.args[1]

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
        assert adapter.get_session_id("123") == "generated_1"
        adapter.send_text.assert_awaited_once_with("123", "已新建并进入会话：my title · generated_1")

    async def test_pending_session_create_pins_new_session_after_switch(self, adapter: TelegramAdapter):
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
        assert adapter.get_session_id("123") == "generated_1"
        adapter.send_text.assert_awaited_once_with(
            "123",
            "已新建并进入会话：我想要一个新会话 · generated_1",
        )

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
        adapter.bind_agent_client(FakeAgent())
        adapter.send_text = AsyncMock()
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "/start"
        update.effective_chat.id = 123
        update.effective_user.id = 456

        await adapter._on_command(update, object())

        adapter.send_text.assert_awaited_once()
        assert "当前故事：Telegram Story" in adapter.send_text.call_args.args[1]
        assert isinstance(adapter.send_text.call_args.kwargs["reply_markup"], InlineKeyboardMarkup)

    async def test_invalid_role_opens_picker_without_sending_turn(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.get_session_overview = AsyncMock(return_value={
            "workspace_id": "tg_workspace",
            "workspace_title": "Workspace",
            "story_id": 1,
            "story_title": "Story",
            "session_id": "tg_default",
            "session_title": "Telegram",
            "player_character_status": "invalid",
            "player_character": None,
            "role_options": [
                {"character_id": 1, "name": "Alice"},
                {"character_id": 2, "name": "Bob"},
            ],
        })
        adapter.bind_agent_client(agent)

        await adapter._on_message(_message_update(123, "继续前进"), object())

        assert not any(call[0] == "stream" for call in agent.calls)
        markup = adapter._app.bot.send_message.call_args.kwargs["reply_markup"]
        assert [row[0].text for row in markup.inline_keyboard] == ["Alice", "Bob"]

    async def test_role_button_binds_and_displays_projected_first_message(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.bind_player_character = AsyncMock(return_value={
            "status": "bound",
            "session_id": "tg_default",
            "player_character_id": 1,
            "player_character": {"character_id": 1, "name": "Alice"},
            "first_message": '<rp-narration>门缓缓打开。</rp-narration>\n<rp-character name="Alice">走吧。</rp-character>',
            "reply": "bound",
        })
        adapter.bind_agent_client(agent)
        await adapter._send_role_picker("123")
        markup = adapter._app.bot.send_message.call_args.kwargs["reply_markup"]
        callback_data = markup.inline_keyboard[0][0].callback_data
        adapter._app.bot.send_message.reset_mock()

        await adapter._on_callback_query(_callback_update(123, callback_data), object())

        agent.bind_player_character.assert_awaited_once_with("tg_default", 1)
        sent_texts = [call.kwargs["text"] for call in adapter._app.bot.send_message.await_args_list]
        assert sent_texts == ["已选择玩家角色：Alice。", "门缓缓打开。\nAlice：走吧。"]

    async def test_help_merges_local_and_current_agent_commands(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent._commands.append(CommandDef(name="/roll", description="掷骰子", detail=""))
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()

        await adapter._on_command(_message_update(123, "/help"), object())

        help_text = adapter.send_text.call_args.args[1]
        assert help_text.count("/help:") == 1
        assert "/clear:" in help_text
        assert "/compact:" in help_text
        assert "/roll: 掷骰子" in help_text

    async def test_help_degrades_to_local_commands(self, adapter: TelegramAdapter):
        agent = FakeAgent()
        agent.list_commands = AsyncMock(side_effect=RuntimeError("offline"))
        adapter.bind_agent_client(agent)
        adapter.send_text = AsyncMock()

        await adapter._on_command(_message_update(123, "/help"), object())

        help_text = adapter.send_text.call_args.args[1]
        assert "/start:" in help_text
        assert "/sessions:" in help_text
        assert "Agent 命令列表暂不可用" in help_text

    async def test_stop_command_bypasses_busy_gate(self, adapter: TelegramAdapter):
        agent = _BlockingAgent()
        adapter.bind_agent_client(agent)
        await adapter._on_message(_message_update(123, "first"), object())
        await agent.started.wait()

        await adapter._on_command(_message_update(123, "/stop"), object())

        stop_calls = [call for call in agent.calls if call[0] == "stop"]
        assert len(stop_calls) == 1
        assert stop_calls[0][1][0] == "tg_default"
        assert stop_calls[0][1][1].startswith("tg_")
        assert adapter._app.bot.edit_message_text.await_args.kwargs["text"] == "已停止"

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
        await _drain_tasks(adapter._app)

        assert agent.calls[-1][0] == "stream"
        assert agent.calls[-1][1][:2] == ("my_tel", "hello")
        assert str(agent.calls[-1][1][2]).startswith("tg_")

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
        agent.initialize = AsyncMock()
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
        assert any(cmd.command == "role_bind" for cmd in commands)
        assert any(cmd.command == "compact" for cmd in commands)
        assert any(cmd.command == "stop" for cmd in commands)
        assert all(cmd.command != "session_switch" for cmd in commands)
        assert all(cmd.command != "memory_reindex" for cmd in commands)
        app.initialize.assert_awaited_once()
        app.start.assert_awaited_once()
        app.updater.start_polling.assert_awaited_once()

    async def test_start_rejects_empty_token(self):
        adapter = TelegramAdapter(token="")

        with pytest.raises(ValueError):
            await adapter.start()

    async def test_stop_cancels_background_turn_before_application_shutdown(
        self,
        adapter: TelegramAdapter,
    ):
        app = adapter._app
        agent = _BlockingAgent()
        adapter.bind_agent_client(agent)
        await adapter._on_message(_message_update(123, "first"), object())
        await agent.started.wait()
        task = app.test_tasks[-1]

        await adapter.stop()

        assert task.cancelled()
        app.updater.stop.assert_awaited_once()
        app.stop.assert_awaited_once()
        app.shutdown.assert_awaited_once()
        assert adapter._app is None
        assert len(adapter._action_registry) == 0

    async def test_stop_continues_cleanup_when_updater_was_not_running(
        self,
        adapter: TelegramAdapter,
    ):
        app = adapter._app
        app.updater.stop = AsyncMock(side_effect=RuntimeError("not running"))

        await adapter.stop()

        app.stop.assert_awaited_once()
        app.shutdown.assert_awaited_once()
        assert adapter._app is None

    async def test_configure_bot_commands_uses_play_allowlist(self, adapter: TelegramAdapter):
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
        assert "valid_cmd" not in command_names
        assert "bad-name" not in command_names
        assert command_names == [
            "start",
            "help",
            "role_bind",
            "sessions",
            "session_create",
            "clear",
            "stop",
        ]

    async def test_non_streaming_menu_does_not_advertise_stop(self, mock_app: MagicMock):
        adapter = TelegramAdapter(
            token="fake:token",
            streaming=False,
            workspace_id="tg_workspace",
            story_id=1,
            session_id="tg_default",
        )
        adapter._app = mock_app
        adapter.bind_agent_client(FakeAgent())

        await adapter._configure_bot_commands()

        commands = adapter._app.bot.set_my_commands.call_args.args[0]
        assert all(command.command != "stop" for command in commands)

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

    async def test_project_rp_output_tags_for_telegram(self):
        text = '<rp-narration>风声停了。</rp-narration>\n<rp-character name="Alice">走吧。</rp-character>'

        projected = project_rp_text(text)
        rendered = render_markdown_to_telegram_html(projected)

        assert rendered == "风声停了。\nAlice：走吧。"

    async def test_project_rp_output_hides_incomplete_stream_tag(self):
        assert project_rp_text('<rp-character name="Ali', streaming=True) == ""
        assert project_rp_text(
            '<rp-character name="Alice">走',
            streaming=True,
        ) == "Alice：走"
        assert project_rp_text(
            '<rp-narration>风起</rp-narr',
            streaming=True,
        ) == "风起"

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
