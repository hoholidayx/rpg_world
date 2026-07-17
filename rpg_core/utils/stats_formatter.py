"""Shared LLM stats formatting — returns strings instead of printing.

Used by both the CLI (``cli.py``) and the API server (``chat.py``) for
consistent display/logging of LLM usage statistics.
"""

from __future__ import annotations

from rpg_core.agent.protocol import AgentStreamEvent
from rpg_core.agent.telemetry import TurnStats


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_cache_hit(usage) -> int:
    """从 LLMUsage 中提取缓存命中 token 数，多来源兜底。"""
    if not usage:
        return 0
    # 1. 标准字段 prompt_cache_hit_tokens
    if usage.prompt_cache_hit_tokens:
        return usage.prompt_cache_hit_tokens
    # 2. prompt_tokens_details.cached_tokens
    if usage.prompt_tokens_details:
        val = usage.prompt_tokens_details.get("cached_tokens", 0)
        if val:
            return int(val)
    # 3. raw_usage（如果有的话）
    if usage.raw_usage:
        val = usage.raw_usage.get("prompt_cache_hit_tokens", 0) or 0
        if val:
            return int(val)
    return 0


def _get_missed_tokens(usage) -> int:
    """Extract prompt cache miss tokens from an LLMUsage object."""
    if not usage:
        return 0
    if usage.prompt_cache_miss_tokens:
        return usage.prompt_cache_miss_tokens
    if usage.raw_usage:
        return int(usage.raw_usage.get("prompt_cache_miss_tokens", 0) or 0)
    return 0


def _format_cache_info(prompt: int, cached: int, missed: int) -> str:
    """Return a compact cache hit/miss summary string — always shown."""
    parts: list[str] = []
    if prompt:
        rate = cached / prompt * 100
        parts.append(f"cache: {cached:,} ({rate:.0f}%)")
    if missed:
        parts.append(f"miss: {missed:,}")
    if parts:
        return "  [" + ", ".join(parts) + "]"
    return ""


# ---------------------------------------------------------------------------
# Public formatters
# ---------------------------------------------------------------------------


def _build_block(
    title: str, calls: list, indent: int = 2,
) -> list[str]:
    """Build a formatted block (main loop or sub-agent) — shared by both formatters."""
    lines: list[str] = []
    prompt = sum(c.usage.prompt_tokens for c in calls if c.usage)
    comp = sum(c.usage.completion_tokens for c in calls if c.usage)
    cached = sum(_get_cache_hit(c.usage) for c in calls if c.usage)
    missed = sum(_get_missed_tokens(c.usage) for c in calls)
    total = prompt + comp
    dur = sum(c.duration_ms for c in calls)
    pad = " " * indent
    lines.append(
        f"{pad}{title} ({len(calls)} call(s)): "
        f"prompt {prompt:,} + completion {comp:,} = {total:,} tokens"
        f"{_format_cache_info(prompt, cached, missed)}"
        f"  |  {dur:.0f}ms"
    )
    for i, c in enumerate(calls):
        u = c.usage
        if not u:
            continue
        p = u.prompt_tokens
        co = u.completion_tokens
        ch = _get_cache_hit(u)
        mi = _get_missed_tokens(u)
        label = c.source if c.source != "chat_loop" else str(i + 1)
        lines.append(
            f"{pad}  [{label}] prompt {p:,} + completion {co:,} = {p + co:,} tokens"
            f"{_format_cache_info(p, ch, mi)}"
            f"  |  {c.duration_ms:.0f}ms  {c.model}"
        )
    return lines


def format_turn_stats(stats: TurnStats) -> str:
    """Format a ``TurnStats`` into a readable multi-line string."""
    lines: list[str] = []
    lines.append("  " + "─" * 50)
    lines.append("  LLM Stats")

    chat_calls = stats.chat_loop_calls
    sub_calls = stats.sub_agent_calls

    if chat_calls:
        lines.extend(_build_block("Main loop", chat_calls))
    if sub_calls:
        lines.extend(_build_block("Sub-agent", sub_calls))

    # 合计
    lines.append("  " + "─" * 50)
    total_pt = stats.total_prompt_tokens
    total_ct = stats.total_completion_tokens
    total_cached = stats.total_cached_tokens
    total_missed = sum(_get_missed_tokens(c.usage) for c in stats.calls)
    lines.append(
        f"  Total: prompt {total_pt:,} + completion {total_ct:,} = {total_pt + total_ct:,} tokens"
        f"{_format_cache_info(total_pt, total_cached, total_missed)}"
        f"  |  {stats.total_duration_ms:.0f}ms"
    )
    first_call = next((c for c in stats.calls if c.model), None)
    if first_call:
        lines.append(f"  Session model: {first_call.model}")
    lines.append("")
    return "\n".join(lines)


def format_event_stats(event: AgentStreamEvent) -> str:
    """Format LLM usage from a DONE ``AgentStreamEvent`` — identical structure to ``format_turn_stats``."""
    if not event.usage:
        return ""

    stats = event.stats
    lines: list[str] = []
    lines.append("  " + "─" * 50)
    lines.append("  LLM Stats")

    if stats:
        chat_calls = stats.chat_loop_calls
        sub_calls = stats.sub_agent_calls
        if chat_calls:
            lines.extend(_build_block("Main loop", chat_calls))
        if sub_calls:
            lines.extend(_build_block("Sub-agent", sub_calls))
    else:
        u = event.usage
        cached = _get_cache_hit(u)
        missed = _get_missed_tokens(u)
        lines.append(
            f"    prompt {u.prompt_tokens:,} + completion {u.completion_tokens:,}"
            f" = {u.total_tokens:,}{_format_cache_info(u.prompt_tokens, cached, missed)}"
        )

    # 合计
    lines.append("  " + "─" * 50)
    if stats:
        total_pt = stats.total_prompt_tokens
        total_ct = stats.total_completion_tokens
        total_cached = stats.total_cached_tokens
        total_missed = sum(_get_missed_tokens(c.usage) for c in stats.calls)
    else:
        u = event.usage
        total_pt = u.prompt_tokens if u else 0
        total_ct = u.completion_tokens if u else 0
        total_cached = u.cached_tokens if u else 0
        total_missed = total_pt - total_cached if total_pt else 0
    lines.append(
        f"  Total: prompt {total_pt:,} + completion {total_ct:,} = {total_pt + total_ct:,} tokens"
        f"{_format_cache_info(total_pt, total_cached, total_missed)}"
        f"  |  {event.duration_ms:.0f}ms"
    )
    if event.model:
        lines.append(f"  Session model: {event.model}")
    lines.append("")
    return "\n".join(lines)
