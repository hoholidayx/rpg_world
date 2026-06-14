"""CommandDispatcher unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from rpg_world.rpg_core.agent.command import CommandDispatcher, format_command_help


class TestCommandDispatcher:
    async def test_help_command_lists_all_commands(self):
        fake_agent = SimpleNamespace(
            clear_history=lambda: None,
            reload_rpg_context=AsyncMock(),
            get_context_markdown=AsyncMock(return_value="context"),
            _memory_manager=None,
            _workspace="data/test",
            _session_id="s1",
            switch_session=AsyncMock(),
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        fake_agent.list_commands = dispatcher.list_commands

        result = await dispatcher.dispatch("/help")

        assert result.handled is True
        assert "可用命令:" in result.reply
        assert "/help" in result.reply
        assert "/clear" in result.reply

    def test_format_command_help(self):
        text = format_command_help([])
        assert text == "当前没有可用命令。"

    async def test_sessions_command_marks_current_session(self, monkeypatch):
        from rpg_world.rpg_core.session import SessionManager

        fake_agent = SimpleNamespace(
            clear_history=lambda: None,
            reload_rpg_context=AsyncMock(),
            get_context_markdown=AsyncMock(return_value="context"),
            _memory_manager=None,
            _workspace="data/test",
            _session_id="s2",
            switch_session=AsyncMock(),
            list_commands=lambda: [],
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        monkeypatch.setattr(SessionManager, "list_sessions", classmethod(lambda cls, workspace: ["s1", "s2"]))

        result = await dispatcher.dispatch("/sessions")

        assert result.handled is True
        assert "当前会话: s2" in result.reply
        assert "- s2 （当前）" in result.reply
