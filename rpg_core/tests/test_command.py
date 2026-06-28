"""CommandDispatcher unit tests."""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from rpg_core.agent import command as command_module
from rpg_core.agent.command import CommandDispatcher, format_command_help
from rpg_data import models


class TestCommandDispatcher:
    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_unknown_slash_command_is_handled_as_error(self):
        dispatcher = CommandDispatcher(agent=SimpleNamespace())
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/cleer")

        assert result.handled is True
        assert "未知命令: /cleer" in result.reply
        assert "/help" in result.reply

    def test_any_leading_slash_input_is_command(self):
        dispatcher = CommandDispatcher(agent=SimpleNamespace())

        assert dispatcher.is_command("/not_registered") is True
        assert dispatcher.is_command("  /not_registered") is True
        assert dispatcher.is_command("not a command") is False

    @pytest.mark.asyncio
    async def test_dispatch_command_edge_cases(self):
        dispatcher = CommandDispatcher(agent=SimpleNamespace())
        dispatcher.register_default_builtins()

        empty = await dispatcher.dispatch("")
        whitespace = await dispatcher.dispatch("   ")
        slash_only = await dispatcher.dispatch("/")

        assert empty.handled is False
        assert whitespace.handled is False
        assert slash_only.handled is True
        assert "未知命令: /" in slash_only.reply

    def test_format_command_help(self):
        text = format_command_help([])
        assert text == "当前没有可用命令。"

    def test_session_id_validation_has_length_limit(self):
        from rpg_core.session import SessionManager

        assert SessionManager.is_valid_session_id("a" * 64)
        assert not SessionManager.is_valid_session_id("a" * 65)
        try:
            SessionManager.validate_session_id("a" * 65)
        except ValueError as exc:
            assert "at most 64 characters" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    @pytest.mark.asyncio
    async def test_sessions_command_marks_current_session(self, monkeypatch):
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

        fake_gateway = SimpleNamespace(
            catalog=SimpleNamespace(
                list_sessions=lambda workspace, story_id: [
                    models.Session("s1", workspace, story_id),
                    models.Session("s2", workspace, story_id),
                ],
            ),
        )
        monkeypatch.setattr(
            command_module,
            "_current_catalog_session",
            lambda agent: (fake_gateway, models.Session("s2", "data/test", 1)),
        )

        result = await dispatcher.dispatch("/sessions")

        assert result.handled is True
        assert "当前会话: s2" in result.reply
        assert "- s2 （当前）" in result.reply
