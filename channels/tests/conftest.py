"""共享测试 fixture 和 mock 辅助类。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from rpg_core.agent.agent_types import (
    AgentStreamEvent,
    StreamEventKind,
    TurnStats,
)
from rpg_core.agent.command import CommandDef, CommandResult
from rpg_core.agent.loop import AgentReply


class FakeAgent:
    """Mock RPGGameAgent，不调真实 LLM。

    模拟 ``send()``、``send_stream()``、``switch_session()`` 等核心方法。
    """

    def __init__(self) -> None:
        self.current_session: str | None = None
        self.history: list[dict] = []
        self._initialized = True
        self._commands = [
            CommandDef(name="/help", description="help", detail="list commands"),
            CommandDef(name="/clear", description="clear", detail="clear history"),
            CommandDef(name="/compact", description="compact", detail="compact history"),
            CommandDef(name="/session_create", description="session create", detail="create session"),
            CommandDef(name="/session_switch", description="session switch", detail="switch session"),
            CommandDef(name="/memory_reindex", description="memory reindex", detail="reindex memory"),
        ]

    async def _ensure_initialized(self) -> None:
        pass

    async def switch_session(self, session_id: str) -> None:
        self.current_session = session_id

    async def send(self, text: str) -> AgentReply:
        return AgentReply(
            text=f"[mock] reply to: {text}",
            stats=TurnStats(),
        )

    async def send_stream(self, text: str) -> AsyncIterator[AgentStreamEvent]:
        """模拟流式输出：一条 text 事件 + 一条 done 事件。"""
        yield AgentStreamEvent(
            kind=StreamEventKind.TEXT,
            content=f"[mock] reply to: {text}",
        )
        yield AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content=f"[mock] reply to: {text}",
        )

    def list_commands(self) -> list[CommandDef]:
        return list(self._commands)

    async def execute_command(self, command: str) -> CommandResult:
        return CommandResult(reply=f"[mock cmd] {command}", handled=True)


class FakeStreamAgent(FakeAgent):
    """模拟多段流式输出的 FakeAgent。"""

    async def send_stream(self, text: str) -> AsyncIterator[AgentStreamEvent]:
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="Hello ")
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="World")
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="!")
        yield AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content="Hello World!",
        )


class FakeErrorAgent(FakeAgent):
    """模拟流式过程中出错的 FakeAgent。"""

    async def send_stream(self, text: str) -> AsyncIterator[AgentStreamEvent]:
        yield AgentStreamEvent(kind=StreamEventKind.ERROR, content="模拟错误")


@dataclass
class FakeBot:
    """Mock telegram.Bot 的行为。"""

    sent_messages: list[dict] = field(default_factory=list)
    edited_messages: list[dict] = field(default_factory=list)
    _message_counter: int = 0

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> object:
        self._message_counter += 1
        msg_id = self._message_counter
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "message_id": msg_id,
            **kwargs,
        })
        return _FakeMessage(msg_id)

    async def edit_message_text(self, chat_id: int, message_id: int, text: str, **kwargs: Any) -> None:
        self.edited_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            **kwargs,
        })


@dataclass
class _FakeMessage:
    """模拟 Message 对象，只有 message_id 属性。"""
    message_id: int


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()
