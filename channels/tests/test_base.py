"""ChannelAdapter 基类单元测试。

所有测试通过 mock 模拟 LLM 回复，无需真实 API key。
"""

from __future__ import annotations

import pytest

from channels.base import ChannelAdapter
from channels.tests.conftest import FakeAgent, FakeStreamAgent, FakeErrorAgent


class RecordingAdapter(ChannelAdapter):
    """用于测试的简单适配器——记录发送行为，不真实发送。"""
    name = "recording"

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[tuple[str, str]] = []
        self.deltas: list[tuple[str, str, bool]] = []
        self.started = False
        self.stopped = False
        self.workspace = "resolved_workspace"

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))

    async def send_delta(self, chat_id: str, delta: str, final: bool = False) -> None:
        self.deltas.append((chat_id, delta, final))
        await super().send_delta(chat_id, delta, final=final)

    def get_workspace(self) -> str:
        return self.workspace


class TestChannelAdapter:
    """ChannelAdapter 基类核心功能测试。"""

    async def test_bind_agent_client(self):
        adapter = RecordingAdapter()
        assert adapter._agent_client is None

        agent = FakeAgent()
        adapter.bind_agent_client(agent)
        assert adapter._agent_client is agent

    async def test_get_session_id(self):
        adapter = RecordingAdapter()
        assert adapter.get_session_id("12345") == "recording_12345"
        assert adapter.get_session_id("abc") == "recording_abc"

    async def test_base_workspace_has_no_legacy_fallback(self):
        class UnresolvedAdapter(RecordingAdapter):
            def get_workspace(self) -> str:
                return ChannelAdapter.get_workspace(self)

        adapter = UnresolvedAdapter()
        with pytest.raises(RuntimeError, match="workspace is not resolved"):
            adapter.get_workspace()

    async def test_start_stop_lifecycle(self):
        adapter = RecordingAdapter()
        assert not adapter.started
        assert not adapter.stopped

        await adapter.start()
        assert adapter.started

        await adapter.stop()
        assert adapter.stopped

    async def test_send_text(self):
        adapter = RecordingAdapter()
        adapter.bind_agent_client(FakeAgent())

        await adapter.send_text("chat1", "hello")
        assert adapter.sent == [("chat1", "hello")]

    async def test_handle_message_non_stream(self):
        """非流式模式下 _handle_message 应调 send() + send_text。"""
        adapter = RecordingAdapter()
        adapter._streaming = False
        adapter.bind_agent_client(FakeAgent())

        reply = await adapter._handle_message("chat1", "user1", "hi")
        assert reply == "[mock] reply to: hi"
        assert adapter.sent == [("chat1", "[mock] reply to: hi")]

    async def test_handle_message_stream(self):
        """流式模式下 _handle_message 应调 send_stream() + send_delta。"""
        adapter = RecordingAdapter()
        adapter._streaming = True
        adapter.bind_agent_client(FakeAgent())

        reply = await adapter._handle_message("chat1", "user1", "hi")
        assert reply == "[mock] reply to: hi"
        # 应有一条 text delta 和一条 final delta
        assert len(adapter.deltas) >= 1
        assert adapter.deltas[-1][2] is True  # last is final

    async def test_handle_message_no_agent_client(self):
        adapter = RecordingAdapter()
        reply = await adapter._handle_message("chat1", "user1", "hi")
        assert reply is None

    async def test_handle_message_passes_session(self):
        adapter = RecordingAdapter()
        agent = FakeAgent()
        adapter.bind_agent_client(agent)

        await adapter._handle_message("chat999", "user1", "hi")
        assert agent.calls[-1] == ("send", ("recording_chat999", "hi"))

    async def test_stream_multiple_deltas(self):
        """多段流式内容应该逐段通过 send_delta 推送。"""
        adapter = RecordingAdapter()
        adapter._streaming = True
        adapter.bind_agent_client(FakeStreamAgent())

        reply = await adapter._handle_message("chat1", "user1", "hi")
        assert reply == "Hello World!"
        assert len(adapter.deltas) == 4  # "Hello " + "World" + "!" + final
        assert adapter.deltas[-1] == ("chat1", "Hello World!", True)

    async def test_stream_error(self):
        """流式出错应发送错误消息。"""
        adapter = RecordingAdapter()
        adapter._streaming = True
        adapter.bind_agent_client(FakeErrorAgent())

        reply = await adapter._handle_message("chat1", "user1", "hi")
        assert reply == ""
        assert len(adapter.sent) == 1
        assert adapter.sent[0][1] == "处理消息失败，请稍后重试。"

    async def test_send_delta_fallback(self):
        """基类 send_delta 默认行为：仅 final=True 时调 send_text。"""
        adapter = RecordingAdapter()
        adapter.bind_agent_client(FakeAgent())

        # 非 final 不应调 send_text
        await adapter.send_delta("chat1", "partial", final=False)
        assert len(adapter.sent) == 0

        # final=True 应调 send_text
        await adapter.send_delta("chat1", "complete", final=True)
        assert adapter.sent == [("chat1", "complete")]

    async def test_default_streaming_flag(self):
        adapter = RecordingAdapter()
        assert adapter._streaming is False  # 默认非流式
