"""CLIAdapter 单元测试。

所有测试 mock LLM 调用，无需 API key。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.cli import CLIAdapter
from channels.tests.conftest import FakeAgent


# 给 FakeAgent 补充命令用到的 clear_history
FakeAgent.clear_history = lambda self: None  # type: ignore[attr-defined]


class TestCLIAdapter:
    """CLIAdapter 核心功能测试。"""

    async def test_get_session_id(self):
        adapter = CLIAdapter(session_id="resolved_session", workspace="data/ws")
        assert adapter.get_session_id("direct") == "resolved_session"

    async def test_get_initial_session_id_uses_adapter_chat_mapping(self):
        adapter = CLIAdapter(session_id="resolved_session", workspace="data/ws")
        assert adapter.get_initial_session_id() == "resolved_session"

    async def test_unresolved_session_raises(self):
        adapter = CLIAdapter()
        with pytest.raises(RuntimeError, match="session is not resolved"):
            adapter.get_session_id("direct")

    async def test_get_session_id_uses_override(self):
        adapter = CLIAdapter(session_id="custom_session")
        assert adapter.get_session_id("direct") == "custom_session"
        assert adapter.get_initial_session_id() == "custom_session"

    async def test_name_constant(self):
        assert CLIAdapter.name == "cli"

    async def test_default_streaming(self):
        adapter = CLIAdapter()
        assert adapter._streaming is True

        adapter2 = CLIAdapter(streaming=False)
        assert adapter2._streaming is False

    async def test_bind_agent_client(self):
        adapter = CLIAdapter()
        assert adapter._agent_client is None
        adapter.bind_agent_client(FakeAgent())
        assert adapter._agent_client is not None

    async def test_send_text(self):
        """send_text 应输出 Panel 格式文本。"""
        adapter = CLIAdapter()
        adapter._console.print = MagicMock()

        await adapter.send_text("direct", "hello")
        call_args = adapter._console.print.call_args
        assert call_args is not None
        panel = call_args[0][0]
        assert panel.renderable == "hello"

    async def test_send_delta_non_final(self):
        """非最终 delta 应传 end=\"\"。"""
        adapter = CLIAdapter()
        adapter._console.print = MagicMock()

        await adapter.send_delta("direct", "abc", final=False)
        kw = adapter._console.print.call_args[1]
        assert kw.get("end") == ""

    async def test_send_delta_final(self):
        """最终 delta 正常换行。"""
        adapter = CLIAdapter()
        adapter._console.print = MagicMock()

        await adapter.send_delta("direct", "abc", final=True)
        adapter._console.print.assert_called_once()

    async def test_start_exits_on_quit(self):
        """输入 /quit 应退出循环。"""
        adapter = CLIAdapter(agent_client=FakeAgent(), session_id="resolved_session", workspace="data/ws")
        adapter._console.print = MagicMock()
        adapter._session.prompt_async = AsyncMock(side_effect=["/quit"])

        await adapter.start()
        assert adapter._running is False
        adapter._session.prompt_async.assert_called_once()
        banner = adapter._console.print.call_args_list[0][0][0]
        assert "/help" in banner

    async def test_handle_message_command(self):
        """命令通过 AgentClient send() 统一处理。"""
        agent = FakeAgent()
        adapter = CLIAdapter(agent_client=agent, streaming=False, session_id="resolved_session", workspace="data/ws")
        adapter._console.print = MagicMock()

        reply = await adapter._handle_message("direct", "user", "/clear")
        # FakeAgent.send() 返回 "[mock] reply to: /clear"
        assert reply == "[mock] reply to: /clear"
        assert agent.calls[-1] == ("send", ("resolved_session", "/clear"))

    async def test_handle_message_command_streaming(self):
        """命令通过 AgentClient stream() 统一处理（流式路径）。"""
        agent = FakeAgent()
        adapter = CLIAdapter(agent_client=agent, streaming=True, session_id="resolved_session", workspace="data/ws")
        adapter._console.print = MagicMock()

        reply = await adapter._handle_message("direct", "user", "/clear")
        # FakeAgent.send_stream() 返回含 "[mock]" 的 DONE 事件
        assert reply is not None
        assert "[mock]" in reply

    async def test_handle_message_no_agent_client(self):
        adapter = CLIAdapter()
        reply = await adapter._handle_message("direct", "user", "hi")
        assert reply is None

    async def test_stop(self):
        adapter = CLIAdapter()
        assert adapter._running is False
        adapter._running = True
        await adapter.stop()
        assert adapter._running is False

    async def test_stream_and_send_uses_send_stream(self):
        """_stream_and_send 应调用 AgentClient stream。"""
        agent = FakeAgent()
        adapter = CLIAdapter(agent_client=agent, session_id="resolved_session", workspace="data/ws")
        adapter._console.print = MagicMock()

        result = await adapter._stream_and_send("direct", "hi")
        assert "[mock] reply to: hi" in result
