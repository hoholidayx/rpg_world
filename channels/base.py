"""ChannelAdapter — 多渠道适配器抽象基类。

子类只需实现 ``start`` / ``stop`` / ``send_text`` 三个抽象方法，
消息处理管线 ``_handle_message`` 由基类统一提供。

Stream 支持通过 ``send_delta`` 可选覆写：默认 fallback 只做一次
``send_text``（非流式行为），子类可覆写实现逐段推送。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from agent_service.client import AgentClient
from rpg_core.agent.agent_types import StreamEventKind
from rpg_core.agent.loop import AgentReply


class ChannelAdapter(ABC):
    """多渠道适配器抽象基类。

    Attributes
    ----------
    name:
        渠道标识名，用于 session_id 前缀和配置查找。
    """

    name: str = "base"

    def __init__(self) -> None:
        self._agent_client: AgentClient | None = None
        self._streaming: bool = False

    # ── 生命周期 ────────────────────────────────────────────────────────

    @abstractmethod
    async def start(self) -> None:
        """启动渠道的长连接（长轮询 / WebSocket / webhook）。"""

    @abstractmethod
    async def stop(self) -> None:
        """优雅关闭渠道连接。"""

    # ── 消息发送 ────────────────────────────────────────────────────────

    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> None:
        """发送完整文本消息。失败必须抛出异常。"""

    async def send_delta(self, chat_id: str, delta: str, final: bool = False) -> None:
        """流式增量发送。

        基类默认行为：仅当 *final* 为 ``True`` 时调用 ``send_text``。
        子类（如 Telegram）应覆写此方法实现逐段编辑。

        Parameters
        ----------
        chat_id:
            目标对话 ID。
        delta:
            本次增量的文本内容。
        final:
            是否为最终增量。最后一次调用时为 ``True``。
        """
        if final:
            await self.send_text(chat_id, delta)

    async def _clear_stream_state(self, chat_id: str) -> None:
        """清理渠道侧的流式状态。

        子类可覆写以释放消息 buffer、编辑句柄等临时状态。
        """
        # 默认无状态可清理。
        return None

    # ── Agent 绑定与 Session 映射 ──────────────────────────────────────

    def bind_agent_client(self, client: AgentClient) -> None:
        """Bind the shared Agent service client."""
        self._agent_client = client

    def get_session_id(self, chat_id: str) -> str:
        """将渠道 chat_id 映射为 agent session_id。

        默认格式 ``"{channel_name}_{chat_id}"``，子类可覆盖。
        """
        return f"{self.name}_{chat_id}"

    def get_workspace(self) -> str:
        """Return the resolved Agent-service workspace for this channel.

        Concrete entrypoints must resolve catalog sessions through
        ``workspace_id + story_id`` and pass the Agent-service workspace into
        their adapter. The base class intentionally has no legacy fallback.
        """
        raise RuntimeError(f"{self.name} workspace is not resolved")

    # ── 消息处理管线 ────────────────────────────────────────────────────

    async def _handle_message(self, chat_id: str, user_id: str, text: str) -> str | None:
        """统一消息处理管线。

        子类收到底层平台事件后调用此方法。处理流程：

        1. 通过 ``get_session_id`` 获取 session_id 并切换
        2. 根据 ``_streaming`` 标志选择流式或非流式处理
        3. 发送回复文本

        Returns
        -------
            回复文本，若被拒绝或无 agent 则返回 ``None``。
        """
        # pylint: disable=unused-argument
        if not self._agent_client:
            return None

        session_id = self.get_session_id(chat_id)
        if self._streaming:
            reply = await self._stream_and_send(chat_id, text)
        else:
            result = await self._agent_client.send(session_id, text)
            reply_text = str(result.get("reply", ""))
            await self.send_text(chat_id, reply_text)
            return reply_text
        return reply.text

    async def _stream_and_send(self, chat_id: str, text: str) -> AgentReply:
        """流式处理 + 逐段推送。

        遍历 ``agent.send_stream()`` 的事件流，通过 ``send_delta``
        实时推送给用户。子类可覆写此方法以实现更精细的流控。

        命令通过 ``send_stream()`` 会直接返回 ``DONE`` 事件（无 ``TEXT``
        事件），此时从 ``DONE.content`` 读取回复内容。
        """
        if not self._agent_client:
            return AgentReply(text="")

        full_text = ""
        event_source = self._agent_client.stream(self.get_session_id(chat_id), text)
        async for event in event_source:
            if event.kind == StreamEventKind.TEXT:
                full_text += event.content
                await self.send_delta(chat_id, event.content, final=False)
            elif event.kind == StreamEventKind.DONE:
                # 命令回复直接带在 DONE.content 中（无 TEXT 事件）
                if not full_text:
                    full_text = event.content
                await self.send_delta(chat_id, full_text, final=True)
                return AgentReply(text=full_text)
            elif event.kind == StreamEventKind.ERROR:
                await self._clear_stream_state(chat_id)
                await self.send_text(chat_id, "处理消息失败，请稍后重试。")
                return AgentReply(text="")
        return AgentReply(text=full_text)
