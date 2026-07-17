"""Typed telemetry records shared by Agent workflows and adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

from llm_client.types import LLMUsage


@dataclass
class CallRecord:
    """Snapshot of one LLM call used by ``TurnStats`` aggregation."""

    source: str
    model: str
    usage: LLMUsage | None = None
    duration_ms: float = 0.0
    reasoning_content: str | None = None

    @property
    def token_summary(self) -> str:
        if self.usage:
            return str(self.usage)
        return "(no usage)"


@dataclass
class TurnStats:
    """Aggregate all LLM calls made while handling one Agent turn."""

    calls: list[CallRecord] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    def add_call(self, record: CallRecord) -> None:
        self.calls.append(record)

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

    def calls_by_source(self, source: str) -> list[CallRecord]:
        return [c for c in self.calls if c.source == source]

    @property
    def chat_loop_calls(self) -> list[CallRecord]:
        return self.calls_by_source("chat_loop")

    @property
    def sub_agent_calls(self) -> list[CallRecord]:
        return [c for c in self.calls if c.source != "chat_loop"]

    def summary(self) -> str:
        cached = self.total_cached_tokens
        missed = self.total_prompt_tokens - cached
        cache_str = (
            f" | cache: {cached:,} hit / {missed:,} miss "
            f"({cached / (cached + missed) * 100:.0f}%)"
            if cached + missed
            else ""
        )
        parts = [
            f"{len(self.calls)} LLM call(s)",
            f"{self.total_prompt_tokens}p + {self.total_completion_tokens}c = "
            f"{self.total_tokens}t{cache_str}",
            f"{self.total_duration_ms:.0f}ms",
        ]
        return " | ".join(parts)
