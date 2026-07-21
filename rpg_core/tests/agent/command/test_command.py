"""CommandDispatcher unit tests."""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from rpg_core.agent.command import CommandDispatcher, format_command_help
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.rp_modules.application import RPModuleApplicationService
from rpg_core.session.reset import SessionResetResult
from rpg_core.settings import RPModuleSettings
from rpg_data import models


class TestCommandDispatcher:
    @pytest.mark.asyncio
    async def test_help_command_lists_all_commands(self):
        fake_agent = SimpleNamespace(
            reset_session=AsyncMock(),
            reload_rpg_context=AsyncMock(),
            get_context_markdown=AsyncMock(return_value="context"),
            session_id="s1",
            reindex_memory=lambda: False,
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
    async def test_clear_command_awaits_complete_session_reset(self):
        fake_agent = SimpleNamespace(reset_session=AsyncMock(return_value=SessionResetResult(
            session_id="s1",
            first_message="新的开场白",
        )))
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/clear")

        assert result.handled is True
        assert "游玩数据已清空" in result.reply
        assert "会话原生状态表已保留并清空值" in result.reply
        assert result.reply.endswith("新的开场白")
        fake_agent.reset_session.assert_awaited_once_with()

        invalid = await dispatcher.dispatch("/clear now")
        assert invalid.reply == "[错误] 用法：/clear"
        fake_agent.reset_session.assert_awaited_once_with()

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
            bind_player_character_by_index=lambda index, opening_index=None: bind_result,
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
            bind_player_character_by_index=lambda index, opening_index=None: SimpleNamespace(
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

    @pytest.mark.asyncio
    async def test_role_bind_forwards_optional_opening_index(self):
        bind_result = SimpleNamespace(
            state=SimpleNamespace(player=SimpleNamespace(name="Alice")),
            first_message="第二开局",
        )
        bind = Mock(return_value=bind_result)
        fake_agent = SimpleNamespace(
            render_role_bind_prompt=lambda error="": "角色列表",
            bind_player_character_by_index=bind,
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/role_bind 1 2")

        assert result.handled is True
        bind.assert_called_once_with(1, 2)
        assert result.role_bind_result is bind_result

    @pytest.mark.asyncio
    async def test_role_bind_forwards_internal_stable_opening_id(self):
        bind_result = SimpleNamespace(
            state=SimpleNamespace(player=SimpleNamespace(name="Alice")),
            first_message="稳定开局",
        )
        bind = Mock(return_value=bind_result)
        fake_agent = SimpleNamespace(
            render_role_bind_prompt=lambda error="": f"角色列表 {error}".strip(),
            bind_player_character_by_index=bind,
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/role_bind 1 opening_id=502")

        assert result.handled is True
        bind.assert_called_once_with(1, story_opening_id=502)
        assert result.role_bind_result is bind_result

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
    async def test_sessions_command_marks_current_session(self):
        fake_agent = SimpleNamespace(
            reset_session=AsyncMock(),
            reload_rpg_context=AsyncMock(),
            get_context_markdown=AsyncMock(return_value="context"),
            session_id="s2",
            reindex_memory=lambda: False,
            list_commands=lambda: [],
            list_story_sessions=lambda: [
                models.Session("s1", "data/test", 1),
                models.Session("s2", "data/test", 1),
            ],
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/sessions")

        assert result.handled is True
        assert "当前会话: s2" in result.reply
        assert "- s2 （当前）" in result.reply

    @pytest.mark.asyncio
    async def test_session_switch_hides_provisioning_target(self):
        fake_agent = SimpleNamespace(
            session_id="s1",
            can_switch_session=lambda _session_id: False,
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/session_switch target")

        assert result.reply == "[会话不存在: target]"
        assert result.active_session is None
        assert fake_agent.session_id == "s1"

    @pytest.mark.asyncio
    async def test_session_switch_returns_locator_without_mutating_source_agent(
        self,
    ):
        fake_agent = SimpleNamespace(
            session_id="s1",
            can_switch_session=lambda session_id: session_id == "target",
        )
        dispatcher = CommandDispatcher(agent=fake_agent)
        dispatcher.register_default_builtins()

        result = await dispatcher.dispatch("/session_switch target")

        assert result.reply == "[已切换到会话: target]"
        assert result.active_session == "target"
        assert fake_agent.session_id == "s1"

    @pytest.mark.asyncio
    async def test_rp_module_commands_are_dispatched(self, tmp_path):
        from rpg_data.services import get_data_service_gateway

        dispatcher = CommandDispatcher(agent=SimpleNamespace())
        dispatcher.register_default_builtins()
        gateway = get_data_service_gateway(tmp_path / "command-rp-modules.sqlite3")
        service = RPModuleApplicationService(
            RPModuleRegistry(settings=RPModuleSettings()),
            gateway.rp_modules,
        )
        for command in service.get_commands("s_forest001"):
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
