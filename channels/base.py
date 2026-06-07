"""ChannelAdapter — 多渠道适配器抽象基类。

子类只需实现 ``start`` / ``stop`` / ``send_text`` 三个抽象方法，
消息处理管线 ``_handle_message`` 由基类统一提供。

Stream 支持通过 ``send_delta`` 可选覆写：默认 fallback 只做一次
``send_text``（非流式行为），子类可覆写实现逐段推送。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from rpg_world.rpg_core.agent.agent_types import StreamEventKind
from rpg_world.rpg_core.agent.loop import AgentReply

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.agent import RPGGameAgent


class ChannelAdapter(ABC):
    """多渠道适配器抽象基类。

    Attributes
    ----------
    name:
        渠道标识名，用于 session_id 前缀和配置查找。
    """

    name: str = "base"

    def __init__(self) -> None:
        self._agent: RPGGameAgent | None = None
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

    # ── Agent 绑定与 Session 映射 ──────────────────────────────────────

    def bind_agent(self, agent: RPGGameAgent) -> None:
        """绑定共享的 RPGGameAgent 实例。"""
        self._agent = agent

    def get_session_id(self, chat_id: str) -> str:
        """将渠道 chat_id 映射为 agent session_id。

        默认格式 ``"{channel_name}:{chat_id}"``，子类可覆盖。
        """
        return f"{self.name}:{chat_id}"

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
        if not self._agent:
            return None

        session_id = self.get_session_id(chat_id)
        await self._agent.switch_session(session_id)

        if self._streaming:
            reply = await self._stream_and_send(chat_id, text)
        else:
            reply = await self._agent.send(text)
            await self.send_text(chat_id, reply.text)
        return reply.text

    async def _stream_and_send(self, chat_id: str, text: str) -> AgentReply:
        """流式处理 + 逐段推送。

        遍历 ``agent.send_stream()`` 的事件流，通过 ``send_delta``
        实时推送给用户。子类可覆写此方法以实现更精细的流控。

        命令通过 ``send_stream()`` 会直接返回 ``DONE`` 事件（无 ``TEXT``
        事件），此时从 ``DONE.content`` 读取回复内容。
        """
        if not self._agent:
            return AgentReply(text="")

        full_text = ""
        async for event in self._agent.send_stream(text):
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
                await self.send_text(chat_id, f"错误: {event.content}")
                return AgentReply(text="")
        return AgentReply(text=full_text)
