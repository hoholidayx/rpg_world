"""Types — 子系统中所有 LLM 调用相关的结构化数据类型。

提供统一的 ``LLMUsage``、``LLMResponse``、``CallRecord``、``TurnStats``，
替代原始 dict 传递，确保 usage / reasoning / timing 数据不被丢弃。

Streaming types:
  - ``ProviderChunk`` — provider 原始 delta chunk
  - ``StreamEventKind`` — 语义事件枚举
  - ``AgentStreamEvent`` — 消费者层面的事件结构
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── LLM 调用 usage 数据 ──────────────────────────────────────────────


@dataclass
class LLMUsage:
    """一次 LLM API 调用的 token 消耗。

    字段对应 OpenAI / DeepSeek ``response.usage`` 结构。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_tokens_details: dict[str, Any] | None = None
    completion_tokens_details: dict[str, Any] | None = None

    @property
    def cached_tokens(self) -> int:
        """取 prompt_tokens_details 中的 cached_tokens（DeepSeek 等）。"""
        if self.prompt_tokens_details:
            return self.prompt_tokens_details.get("cached_tokens", 0)
        return 0

    @property
    def has_usage(self) -> bool:
        """API 是否返回了 usage 数据。"""
        return self.total_tokens > 0 or self.prompt_tokens_details is not None

    def __str__(self) -> str:
        parts = [f"{self.prompt_tokens}p + {self.completion_tokens}c = {self.total_tokens}t"]
        cached = self.cached_tokens
        if cached:
            parts.append(f" [cache: {cached} hit]")
        return "".join(parts)


# ── LLM 响应封装 ──────────────────────────────────────────────────────


@dataclass
class LLMResponse:
    """替换 ``dict[str, Any]`` 作为 ``LLMProvider.chat()`` 的返回类型。

    包含 content/tool_calls 以及 usage/model/reasoning 等元数据。
    """

    content: str
    tool_calls: list[dict[str, Any]] | None
    finish_reason: str | None
    usage: LLMUsage | None = None
    model: str | None = None
    request_id: str | None = None
    created: int | None = None
    reasoning_content: str | None = None


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
    """一次 ``send()`` / ``single_turn()`` 中所有 LLM 调用的聚合。

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
        parts = [
            f"{len(self.calls)} LLM call(s)",
            f"{self.total_prompt_tokens}p + {self.total_completion_tokens}c = {self.total_tokens}t",
        ]
        cached = self.total_cached_tokens
        if cached:
            parts.append(f"cache: {cached} hit")
        parts.append(f"{self.total_duration_ms:.0f}ms")
        return " | ".join(parts)


# ── 流式输出类型 ──────────────────────────────────────────────────────


@dataclass
class ProviderChunk:
    """Provider 层原始 streaming delta chunk。

    由 ``LLMProvider.chat_stream()`` 产出，每对应一次 API chunk。
    ``tool_calls`` / ``usage`` / ``model`` / ``finish_reason`` 仅在末 chunk 非空。
    """

    content: str = ""
    reasoning_content: str | None = None

    # 以下只在末 chunk 非空：
    tool_calls: list[dict] | None = None
    finish_reason: str | None = None
    usage: LLMUsage | None = None
    model: str | None = None
    request_id: str | None = None
    created: int | None = None


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
    reasoning_content: str | None = None
    stats: TurnStats | None = None
    """完整 LLM 调用明细（含 SubAgent 细分）。仅在 DONE 事件携带。"""
