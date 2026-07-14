"""CommandDispatcher unit tests."""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from rpg_core.agent import command as command_module
from rpg_core.agent.command import CommandDispatcher, format_command_help
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.settings import RPModuleSettings
from rpg_data import models


class TestCommandDispatcher:
    @pytest.mark.asyncio
    async def test_help_command_lists_all_commands(self):
        fake_agent = SimpleNamespace(
            clear_history=lambda: None,
            reload_rpg_context=AsyncMock(),
            get_context_markdown=AsyncMock(return_value="context"),
            session_id="s1",
            reindex_memory=lambda: False,
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

    @pytest.mark.asyncio
    async def test_context_command_defaults_to_markdown(self):
        fake_agent = SimpleNamespace(
            get_context_markdown=AsyncMock(return_value="markdown context"),
            get_context_json=AsyncMock(return_value='{"ok": true}'),
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/context")

        assert result.handled is True
        assert result.reply == "markdown context"
        fake_agent.get_context_markdown.assert_awaited_once()
        fake_agent.get_context_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_context_command_supports_json_flag(self):
        fake_agent = SimpleNamespace(
            get_context_markdown=AsyncMock(return_value="markdown context"),
            get_context_json=AsyncMock(return_value='{"formatVersion": "context-preview.v1"}'),
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/context --json")

        assert result.handled is True
        assert result.reply == '{"formatVersion": "context-preview.v1"}'
        fake_agent.get_context_json.assert_awaited_once()
        fake_agent.get_context_markdown.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_context_command_rejects_unknown_args(self):
        fake_agent = SimpleNamespace(
            get_context_markdown=AsyncMock(return_value="markdown context"),
            get_context_json=AsyncMock(return_value='{"ok": true}'),
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/context --bad")

        assert result.handled is True
        assert result.reply == "[错误] 用法：/context [--json]"
        fake_agent.get_context_markdown.assert_not_awaited()
        fake_agent.get_context_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_role_bind_lists_options_without_llm(self):
        fake_agent = SimpleNamespace(
            render_role_bind_prompt=lambda error="": f"角色列表 {error}".strip(),
            bind_player_character_by_index=lambda index: None,
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/role_bind")

        assert result.handled is True
        assert result.reply == "角色列表"

    @pytest.mark.asyncio
    async def test_role_bind_rejects_invalid_index_text(self):
        fake_agent = SimpleNamespace(
            render_role_bind_prompt=lambda error="": f"角色列表 {error}".strip(),
            bind_player_character_by_index=lambda index: None,
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/role_bind Alice")

        assert result.handled is True
        assert "无效角色序号: Alice" in result.reply

    @pytest.mark.asyncio
    async def test_role_bind_returns_first_message_when_appended(self):
        bind_result = SimpleNamespace(
            state=SimpleNamespace(player=SimpleNamespace(name="Alice")),
            first_message="开场白",
        )
        fake_agent = SimpleNamespace(
            render_role_bind_prompt=lambda error="": "角色列表",
            bind_player_character_by_index=lambda index: bind_result,
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/role_bind 1")

        assert result.handled is True
        assert result.reply == "已绑定/切换扮演角色：Alice。\n\n开场白"
        assert result.role_bind_result is bind_result

    @pytest.mark.asyncio
    async def test_role_bind_returns_switch_confirmation(self):
        fake_agent = SimpleNamespace(
            render_role_bind_prompt=lambda error="": "角色列表",
            bind_player_character_by_index=lambda index: SimpleNamespace(
                state=SimpleNamespace(player=SimpleNamespace(name="Bob")),
                first_message="",
            ),
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/role_bind 2")

        assert result.handled is True
        assert result.reply == (
            "已绑定/切换扮演角色：Bob。 "
            "后续消息将使用该身份；已有历史不会被改写。"
        )

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
            session_id="s2",
            reindex_memory=lambda: False,
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

    @pytest.mark.asyncio
    async def test_rp_module_commands_are_dispatched(self, tmp_path):
        from rpg_data.services import get_data_service_gateway

        dispatcher = CommandDispatcher(agent=SimpleNamespace())
        dispatcher.register_default_builtins()
        gateway = get_data_service_gateway(tmp_path / "command-rp-modules.sqlite3")
        registry = RPModuleRegistry(
            settings=RPModuleSettings(),
            gateway_provider=lambda: gateway,
        )
        for command in registry.get_commands("s_forest001"):
            dispatcher.register_builtin(
                command.name,
                command.description,
                command.detail,
                command.handler,
            )

        commands = dispatcher.list_commands()
        assert "/check_dc" in [command.name for command in commands]
        assert "/check" not in [command.name for command in commands]

        roll = await dispatcher.dispatch("/roll 1d2")
        check = await dispatcher.dispatch("/check_dc 1d2 dc=1")

        assert roll.handled is True
        assert "骰子结果:" in roll.reply
        assert check.handled is True
        assert "检定结果:" in check.reply
