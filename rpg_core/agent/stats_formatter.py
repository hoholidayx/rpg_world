"""Shared LLM stats formatting — returns strings instead of printing.

Used by both the CLI (``cli.py``) and the API server (``chat.py``) for
consistent display/logging of LLM usage statistics.
"""

from __future__ import annotations

from rpg_world.rpg_core.agent.agent_types import AgentStreamEvent, TurnStats


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_cache_info(prompt: int, cached: int, missed: int) -> str:
    """Return a compact cache hit/miss summary string."""
    parts: list[str] = []
    if cached:
        rate = cached / prompt * 100
        parts.append(f"cache: {cached:,} ({rate:.0f}%)")
    if missed:
        parts.append(f"miss: {missed:,}")
    if parts:
        return "  [" + ", ".join(parts) + "]"
    return ""


def _get_missed_tokens(usage) -> int:
    """Extract prompt cache miss tokens from an LLMUsage object."""
    return usage.prompt_cache_miss_tokens if usage else 0


# ---------------------------------------------------------------------------
# Public formatters
# ---------------------------------------------------------------------------


def format_turn_stats(stats: TurnStats) -> str:
    """Format a ``TurnStats`` object into a human-readable string.

    Replaces ``_print_stats()`` in ``cli.py``.  Returns a multi-line string
    with the LLM stats panel (same structure as the CLI output).
    """
    lines: list[str] = []
    lines.append("  " + "─" * 50)
    lines.append("  LLM Stats")

    chat_calls = stats.chat_loop_calls
    sub_calls = stats.sub_agent_calls

    if chat_calls:
        chat_prompt = sum(c.usage.prompt_tokens for c in chat_calls if c.usage)
        chat_comp = sum(c.usage.completion_tokens for c in chat_calls if c.usage)
        chat_cached = sum(c.usage.cached_tokens for c in chat_calls if c.usage)
        chat_missed = sum(_get_missed_tokens(c.usage) for c in chat_calls)
        chat_total = chat_prompt + chat_comp
        chat_dur = sum(c.duration_ms for c in chat_calls)
        lines.append(
            f"    Main loop ({len(chat_calls)} call(s)): "
            f"prompt {chat_prompt:,} + completion {chat_comp:,} = total {chat_total:,} tokens"
            f"{_format_cache_info(chat_prompt, chat_cached, chat_missed)}"
            f"  |  {chat_dur:.0f}ms"
        )
        for i, c in enumerate(chat_calls):
            u = c.usage
            if not u:
                continue
            prompt_n = u.prompt_tokens
            comp_n = u.completion_tokens
            cached_n = u.cached_tokens
            missed_n = _get_missed_tokens(u)
            lines.append(
                f"      [{i+1}] prompt {prompt_n:,} + completion {comp_n:,} = {prompt_n + comp_n:,} tokens"
                f"{_format_cache_info(prompt_n, cached_n, missed_n)}"
                f"  |  {c.duration_ms:.0f}ms  [model: {c.model}]"
            )

    if sub_calls:
        sub_prompt = sum(c.usage.prompt_tokens for c in sub_calls if c.usage)
        sub_comp = sum(c.usage.completion_tokens for c in sub_calls if c.usage)
        sub_cached = sum(c.usage.cached_tokens for c in sub_calls if c.usage)
        sub_missed = sum(_get_missed_tokens(c.usage) for c in sub_calls)
        sub_total = sub_prompt + sub_comp
        sub_dur = sum(c.duration_ms for c in sub_calls)
        lines.append(
            f"    Sub-agent ({len(sub_calls)} call(s)): "
            f"prompt {sub_prompt:,} + completion {sub_comp:,} = total {sub_total:,} tokens"
            f"{_format_cache_info(sub_prompt, sub_cached, sub_missed)}"
            f"  |  {sub_dur:.0f}ms"
        )
        for c in sub_calls:
            u = c.usage
            if not u:
                continue
            prompt_n = u.prompt_tokens
            comp_n = u.completion_tokens
            cached_n = u.cached_tokens
            missed_n = _get_missed_tokens(u)
            lines.append(
                f"      [{c.source}] prompt {prompt_n:,} + completion {comp_n:,} = {prompt_n + comp_n:,} tokens"
                f"{_format_cache_info(prompt_n, cached_n, missed_n)}"
                f"  |  {c.duration_ms:.0f}ms  [model: {c.model}]"
            )

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
    lines.append("")

    return "\n".join(lines)


def format_event_stats(event: AgentStreamEvent) -> str:
    """Format LLM usage from a DONE ``AgentStreamEvent`` into a human-readable string.

    Groups calls by source (chat_loop vs sub-agents), shows per-call
    detail, and computes cache hit rate percentage.

    Replaces ``_print_event_stats()`` in ``cli.py``.
    """
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
            chat_prompt = sum(c.usage.prompt_tokens for c in chat_calls if c.usage)
            chat_comp = sum(c.usage.completion_tokens for c in chat_calls if c.usage)
            chat_total = chat_prompt + chat_comp
            chat_dur = sum(c.duration_ms for c in chat_calls)
            lines.append(
                f"  Main loop ({len(chat_calls)} call(s)): "
                f"prompt {chat_prompt:,} + completion {chat_comp:,} = {chat_total:,} tokens"
                f"  |  {chat_dur:.0f}ms"
            )
            for i, c in enumerate(chat_calls):
                p = c.usage.prompt_tokens if c.usage else 0
                co = c.usage.completion_tokens if c.usage else 0
                cached = c.usage.cached_tokens if c.usage else 0
                rate = (cached / p * 100) if p else 0
                suffix = f"  cache: {cached:,} ({rate:.0f}%)" if cached else ""
                lines.append(
                    f"    [{i+1}] prompt {p:,} + completion {co:,} = {p+co:,} tokens"
                    f"  |  {c.duration_ms:.0f}ms  {c.model}{suffix}"
                )

        if sub_calls:
            sub_prompt = sum(c.usage.prompt_tokens for c in sub_calls if c.usage)
            sub_comp = sum(c.usage.completion_tokens for c in sub_calls if c.usage)
            sub_total = sub_prompt + sub_comp
            sub_dur = sum(c.duration_ms for c in sub_calls)
            lines.append(
                f"  Sub-agent ({len(sub_calls)} call(s)): "
                f"prompt {sub_prompt:,} + completion {sub_comp:,} = {sub_total:,} tokens"
                f"  |  {sub_dur:.0f}ms"
            )
            for c in sub_calls:
                p = c.usage.prompt_tokens if c.usage else 0
                co = c.usage.completion_tokens if c.usage else 0
                cached = c.usage.cached_tokens if c.usage else 0
                rate = (cached / p * 100) if p else 0
                suffix = f"  cache: {cached:,} ({rate:.0f}%)" if cached else ""
                lines.append(
                    f"    [{c.source}] prompt {p:,} + completion {co:,} = {p+co:,} tokens"
                    f"  |  {c.duration_ms:.0f}ms  {c.model}{suffix}"
                )
    else:
        # Fallback: just show aggregate usage
        u = event.usage
        cached = u.cached_tokens
        rate = (cached / u.prompt_tokens * 100) if u.prompt_tokens else 0
        cache_str = f", cache: {cached:,} ({rate:.0f}%)" if cached else ""
        lines.append(f"    prompt: {u.prompt_tokens:,}{cache_str}")
        lines.append(f"    completion: {u.completion_tokens:,}")
        lines.append(f"    total: {u.total_tokens:,}")

    # ── Total summary with cache rate ──────────────────────────────
    lines.append("  " + "─" * 50)
    u = event.usage
    total_cached = u.cached_tokens if u else 0
    total_prompt = u.prompt_tokens if u else 0
    total_comp = u.completion_tokens if u else 0
    total_tokens = u.total_tokens if u else 0
    cache_rate = (total_cached / total_prompt * 100) if total_prompt else 0
    cache_str = f"  |  cache: {total_cached:,} ({cache_rate:.0f}%)" if total_cached else ""
    lines.append(
        f"  Total: prompt {total_prompt:,} + completion {total_comp:,} = {total_tokens:,} tokens"
        f"{cache_str}  |  {event.duration_ms:.0f}ms"
    )
    if event.model:
        lines.append(f"  Session model: {event.model}")
    lines.append("")

    return "\n".join(lines)
