"""Types — 子系统中所有 LLM 调用相关的结构化数据类型。

提供统一的 ``LLMUsage``、``LLMResponse``、``CallRecord``、``TurnStats``，
替代原始 dict 传递，确保 usage / reasoning / timing 数据不被丢弃。

Streaming types:
  - ``ProviderChunk`` — provider 原始 delta chunk
  - ``StreamEventKind`` — 语义事件枚举
  - ``AgentStreamEvent`` — 消费者层面的事件结构

Queue types:
  - ``QueueItem`` — 消息队列工作项
  - ``_StreamSentinel`` — send_stream 事件流结束标记
  - ``TurnCancelResult`` — active/queued turn cancellation result
"""

from __future__ import annotations

import time
from asyncio import Queue as AsyncQueue
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from llm_client.types import LLMResponse, LLMUsage, ProviderChunk
from rpg_core.agent.turn.models import TurnRequest


# ── 一次 LLM 调用的记录 ──────────────────────────────────────────────


@dataclass
class CallRecord:
    """一次 LLM API 调用的快照——用于 ``TurnStats`` 聚合。"""

    source: str
    """调用来源：``"chat_loop"`` / ``"status_sub_agent"`` / ``"memory_recall"`` 等。"""
    model: str
    """实际使用的模型名。"""
    usage: LLMUsage | None = None
    duration_ms: float = 0.0
    reasoning_content: str | None = None

    @property
    def token_summary(self) -> str:
        if self.usage:
            return str(self.usage)
        return "(no usage)"


# ── 一次 send() 的聚合统计 ────────────────────────────────────────────


@dataclass
class TurnStats:
    """一次 ``send()`` 中所有 LLM 调用的聚合。

    Usage::

        stats = TurnStats(started_at=time.monotonic())
        # ... 执行各 LLM 调用，stats.add_call(...) ...
        stats.finished_at = time.monotonic()
        print(stats.summary())
    """

    calls: list[CallRecord] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    def add_call(self, record: CallRecord) -> None:
        """追加一次 LLM 调用记录。"""
        self.calls.append(record)

    # ── 计算属性 ────────────────────────────────────────────────────

    @property
    def total_duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000

    @property
    def total_prompt_tokens(self) -> int:
        return sum(c.usage.prompt_tokens for c in self.calls if c.usage)

    @property
    def total_completion_tokens(self) -> int:
        return sum(c.usage.completion_tokens for c in self.calls if c.usage)

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    @property
    def total_cached_tokens(self) -> int:
        return sum(c.usage.cached_tokens for c in self.calls if c.usage)

    # ── 分组访问 ────────────────────────────────────────────────────

    def calls_by_source(self, source: str) -> list[CallRecord]:
        return [c for c in self.calls if c.source == source]

    @property
    def chat_loop_calls(self) -> list[CallRecord]:
        return self.calls_by_source("chat_loop")

    @property
    def sub_agent_calls(self) -> list[CallRecord]:
        return [
            c for c in self.calls
            if c.source != "chat_loop"
        ]

    # ── 展示 ─────────────────────────────────────────────────────────

    def summary(self) -> str:
        """返回一行摘要文本。"""
        cached = self.total_cached_tokens
        missed = self.total_prompt_tokens - cached
        cache_str = f" | cache: {cached:,} hit / {missed:,} miss ({cached/(cached+missed)*100:.0f}%)" if (cached + missed) else ""
        parts = [
            f"{len(self.calls)} LLM call(s)",
            f"{self.total_prompt_tokens}p + {self.total_completion_tokens}c = {self.total_tokens}t{cache_str}",
        ]
        parts.append(f"{self.total_duration_ms:.0f}ms")
        return " | ".join(parts)


class StreamEventKind(str, Enum):
    """流式事件的语义类型枚举。"""

    TEXT = "text"
    """文本增量——逐 chunk 实时显示。"""
    THINKING = "thinking"
    """推理/思考增量（DeepSeek R1 等）。"""
    TOOL_CALL = "tool_call"
    """模型发起了一个 tool call。"""
    TOOL_RESULT = "tool_result"
    """一个 tool 执行完毕，结果可供显示。"""
    ROUND_START = "round_start"
    """一轮新 LLM 生成开始（多轮 tool calling 时标记 phase）。"""
    ROUND_END = "round_end"
    """一轮 LLM 生成结束。"""
    DONE = "done"
    """流结束——携带完整 reply 文本和聚合元数据。"""
    ERROR = "error"
    """流式过程中发生错误。"""


@dataclass
class AgentStreamEvent:
    """消费者层面的语义事件。

    Consumer 通过 ``match event.kind`` 分支处理：:

        async for event in agent.send_stream("hello"):
            match event.kind:
                case StreamEventKind.TEXT:
                    print(event.content, end="", flush=True)
                case StreamEventKind.DONE:
                    ...
    """

    kind: StreamEventKind
    content: str = ""
    error_code: str | None = None
    status_code: int | None = None

    # ── TOOL_CALL 字段 ─────────────────────────────────────────────
    tool_name: str | None = None
    tool_arguments: str | None = None
    tool_call_id: str | None = None

    # ── TOOL_RESULT 字段 ───────────────────────────────────────────
    tool_result: str | None = None
    tool_result_preview: str | None = None

    # ── 轮次跟踪 ──────────────────────────────────────────────────
    round_index: int = 0

    # ── 流结束后才收齐的元数据（DONE 事件携带） ─────────────────
    usage: LLMUsage | None = None
    model: str | None = None
    finish_reason: str | None = None
    duration_ms: float = 0.0
    committed_turn_id: int | None = None
    reasoning_content: str | None = None
    stats: TurnStats | None = None
    """完整 LLM 调用明细（含 SubAgent 细分）。仅在 DONE 事件携带。"""

    def to_dict(self) -> dict[str, object]:
        """序列化为 JSON-safe dict，供 SSE 传输。"""
        d: dict[str, object] = {"kind": self.kind.value}
        if self.content:
            d["content"] = self.content
        if self.error_code:
            d["error_code"] = self.error_code
        if self.status_code:
            d["status_code"] = int(self.status_code)
        if self.tool_name:
            d["tool_name"] = self.tool_name
        if self.tool_arguments:
            d["tool_arguments"] = self.tool_arguments
        if self.tool_result_preview:
            d["tool_result_preview"] = self.tool_result_preview
        if self.tool_result:
            d["tool_result"] = self.tool_result
        if self.round_index:
            d["round_index"] = self.round_index
        if self.usage:
            from rpg_core.context.usage import usage_to_wire_payload

            d["usage"] = usage_to_wire_payload(
                self.usage,
                model=self.model,
                finish_reason=self.finish_reason,
                duration_ms=self.duration_ms or None,
            )
        if self.duration_ms:
            d["duration_ms"] = round(self.duration_ms, 1)
        if self.model:
            d["model"] = self.model
        if self.finish_reason:
            d["finish_reason"] = self.finish_reason
        if self.committed_turn_id is not None:
            if self.committed_turn_id <= 0:
                raise ValueError("committed_turn_id must be a positive integer")
            d["committed_turn_id"] = int(self.committed_turn_id)
        return d


# ── 消息队列类型 ──────────────────────────────────────────────────────────


class QueueKind(StrEnum):
    """队列工作项类型常量——替代 magic string。

    使用 ``StrEnum`` 而非模块级常量，是因为：
    1. Python 的 ``match/case`` 需要点号名（dotted name）才能做值比较而非捕获
    2. ``kind: QueueKind`` 可作为类型注解，替代 ``Literal["send", "send_stream", "command"]``
    """

    SEND = "send"
    """``send()`` 请求。"""
    SEND_STREAM = "send_stream"
    """``send_stream()`` 请求。"""
    COMMAND = "command"
    """``execute_command()`` 请求。"""
    TRUNCATE_HISTORY = "truncate_history"
    """截断当前会话历史。"""


class TurnCancelStatus(StrEnum):
    """Result status for best-effort turn cancellation."""

    CANCELLED = "cancelled"
    """An active or queued stream request was cancelled."""
    NOT_RUNNING = "not_running"
    """No matching active or queued stream request exists."""
    STALE = "stale"
    """The supplied request id does not match the active stream request."""


@dataclass(frozen=True)
class TurnCancelResult:
    """Best-effort cancellation outcome for one agent turn."""

    status: TurnCancelStatus
    session_id: str
    request_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "status": self.status.value,
            "session_id": self.session_id,
        }
        if self.request_id:
            data["request_id"] = self.request_id
        return data


@dataclass
class QueueItem:
    """消息队列工作项——send / send_stream / command 的入队单元。

    Attributes
    ----------
    kind:
        工作项类型。使用 ``QueueKind.*`` 常量赋值。
    future:
        用于返回结果的 Future。send → ``Future[AgentReply]``，command → ``Future[CommandResult]``。
    turn_request:
        仅 ``send`` / ``send_stream`` 使用的规范化请求，是正文与 request ID 的唯一真源。
    command:
        仅 ``command`` 使用的完整命令。
    event_queue:
        仅 ``send_stream`` 使用：消费者向此队列推入事件，主协程从中读取并 yield。
    turn_id:
        仅历史截断工作项使用。
    """

    kind: QueueKind
    future: Future
    turn_request: TurnRequest | None = None
    command: str | None = None
    event_queue: AsyncQueue | None = None
    turn_id: int | None = None

    @property
    def request_id(self) -> str | None:
        return self.turn_request.request_id if self.turn_request is not None else None

    @property
    def input_text(self) -> str:
        if self.turn_request is not None:
            return self.turn_request.text
        return self.command or ""


class _StreamSentinel:
    """标记 ``send_stream`` 事件流的结束。"""

    pass
