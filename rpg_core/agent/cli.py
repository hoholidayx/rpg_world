"""CLI entry point for testing the standalone RPG agent.

Usage:

    # Interactive REPL (default)
    uv run python -m rpg_world.agent.cli [--model gpt-4o] [--session-id default] ...

    # Single-turn mode — send one message and exit
    uv run python -m rpg_world.agent.cli --single-turn "look around the room"

Interactive commands:
  /clear         — reset conversation history
  /reload        — reload RPG context from disk
  /history       — print raw history
  /context       — show current context structure and token usage
  /compact [N] [K] — compress oldest N user rounds into summary, keep K rounds
  /quit          — exit
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rpg_world.rpg_core.agent import RPGGameAgent
from rpg_world.rpg_core.agent.agent_types import StreamEventKind, TurnStats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG Agent CLI")
    parser.add_argument("--model", default="deepseek-v4-flash", help="OpenAI model name")
    parser.add_argument("--session-id", default="default", help="Session identifier")
    parser.add_argument("--api-key", default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    parser.add_argument("--base-url", default="https://api.deepseek.com", help="OpenAI-compatible base URL")
    parser.add_argument("--max-tokens", type=int, default=None, help="Max tokens per response")
    parser.add_argument("--temperature", type=float, default=None, help="Sampling temperature")
    parser.add_argument("--single-turn", "-m", type=str, default=None,
                        help="Single-turn mode: send one message and exit")
    parser.add_argument("--stream", "-s", action="store_true",
                        help="Stream output progressively (default: on in REPL)")
    return parser.parse_args()


async def _repl(agent: RPGGameAgent, stream: bool = True) -> None:
    print("RPG Agent ready.  Commands: /clear  /reload  /history  /context  /compact  /sessions  /session-create  /session-switch  /quit")
    if stream:
        print("Streaming mode: text appears progressively as the LLM generates it.")
    print()

    while True:
        try:
            raw = await asyncio.to_thread(sys.stdin.readline)
        except EOFError:
            break
        if not raw:
            break

        text = raw.strip()
        if not text:
            continue

        # ── built-in commands ──────────────────────────────────────
        if text == "/quit":
            break
        if text == "/clear":
            agent.clear_history()
            print("[history cleared]\n")
            continue
        if text == "/reload":
            await agent.reload_rpg_context()
            print("[RPG context reloaded]\n")
            continue
        if text == "/history":
            for i, msg in enumerate(agent.history):
                role = msg["role"]
                preview = (msg.get("content") or "")[:80]
                print(f"  [{i}] {role}: {preview}...")
            print()
            continue
        if text == "/context":
            md = await agent.get_context_markdown()
            print()
            print(md)
            print()
            continue
        if text == "/sessions":
            from rpg_world.rpg_core.settings import settings

            sessions = settings.list_sessions()
            current = agent._session_id  # type: ignore[attr-defined]
            print(f"Sessions ({len(sessions)}):")
            for s in sessions:
                marker = "  *" if s == current else ""
                print(f"  - {s}{marker}")
            print()
            continue
        if text.startswith("/session-create "):
            parts = text.split(maxsplit=1)
            sid = parts[1].strip()
            if not sid:
                print("[error] session id is required\n")
                continue
            from rpg_world.rpg_core.settings import settings

            try:
                settings.create_session(sid)
                print(f"[session created: {sid}]\n")
            except FileExistsError:
                print(f"[session already exists: {sid}]\n")
            continue
        if text.startswith("/session-switch "):
            parts = text.split(maxsplit=1)
            sid = parts[1].strip()
            if not sid:
                print("[error] session id is required\n")
                continue
            from rpg_world.rpg_core.settings import settings

            if sid not in settings.list_sessions():
                print(f"[session not found: {sid}]\n")
                continue
            await agent.switch_session(sid)
            print(f"[switched to session: {sid}]\n")
            continue

        # ── /compact ──────────────────────────────────────────────────
        if text == "/compact" or text.startswith("/compact "):
            parts = text.split()
            compress_rounds: int | None = None
            keep_rounds: int | None = None
            if len(parts) >= 2:
                try:
                    compress_rounds = int(parts[1])
                except ValueError:
                    print("[error] compress_rounds must be an integer\n")
                    continue
            if len(parts) >= 3:
                try:
                    keep_rounds = int(parts[2])
                except ValueError:
                    print("[error] keep_rounds must be an integer\n")
                    continue
            result = await agent.compact_history(compress_rounds, keep_rounds)
            if result.get("skipped"):
                print(f"[compact skipped] {result['reason']}\n")
            else:
                summary_text = result.get("summary_text", "")
                if summary_text:
                    print(f"  ── Summary ({result['compress_rounds']} rounds compressed) ──\n")
                    print(f"  {summary_text[:500]}")
                    if len(summary_text) > 500:
                        print("  ...")
                else:
                    print(f"  ── Summary ({result['compress_rounds']} rounds compressed, empty) ──")
                print()
                print(f"  History: {result['previous_history_msgs']} → {result['history_after_msgs']} msgs")
            print()
            continue

        if stream:
            # ── streaming chat ─────────────────────────────────────
            await _handle_streaming_chat(agent, text)
        else:
            # ── normal chat (buffered) ──────────────────────────────
            await _handle_buffered_chat(agent, text)


async def _handle_streaming_chat(agent: RPGGameAgent, text: str) -> None:
    """Send message via streaming path and render events in real-time."""
    try:
        async for event in agent.send_stream(text):
            if event.kind == StreamEventKind.TEXT:
                print(event.content, end="", flush=True)
            elif event.kind == StreamEventKind.THINKING:
                # Gray/italic for thinking content
                print(f"\033[2m{event.content}\033[0m", end="", flush=True)
            elif event.kind == StreamEventKind.TOOL_CALL:
                print(f"\n  ── [{event.tool_name}({event.tool_arguments})]")
            elif event.kind == StreamEventKind.TOOL_RESULT:
                preview = event.tool_result_preview or (event.tool_result or "")[:200]
                print(f"     → {preview}")
            elif event.kind == StreamEventKind.ROUND_START:
                if event.round_index > 0:
                    print(f"\n  ── round {event.round_index} ──\n")
            elif event.kind == StreamEventKind.DONE:
                print()  # newline after streaming text
                if event.usage:
                    _print_event_stats(event)
            elif event.kind == StreamEventKind.ERROR:
                print(f"\n[stream error] {event.content}\n")
    except Exception as exc:
        print(f"\n[error] {exc}\n")


async def _handle_buffered_chat(agent: RPGGameAgent, text: str) -> None:
    """Send message via buffered path and print full reply."""
    try:
        reply = await agent.send(text)
    except Exception as exc:
        print(f"[error] {exc}\n")
        return

    # ── status sub-agent records ───────────────────────────────
    if reply.status_sub_agent_records:
        tools_str = ', '.join(
            f"{r['tool_name']}({r['arguments']})"
            for r in reply.status_sub_agent_records
        )
        print(f"  ── StatusSubAgent: {tools_str}")
        for r in reply.status_sub_agent_records:
            result_preview = r['result'][:120]
            print(f"     → {result_preview}")
        print()

    # ── tool call records ──────────────────────────────────────
    if reply.tool_records:
        for i, rec in enumerate(reply.tool_records):
            tool_names = []
            for tc in rec.assistant_message.get("tool_calls", []):
                tool_names.append(tc["function"]["name"])
            print(f"  ── tool call [{i+1}]: {', '.join(tool_names)}")
            if rec.reasoning_content:
                print(f"     [thinking] {rec.reasoning_content[:200]}")
            for tr in rec.tool_results:
                print(f"     → {tr['content']}")
        print()

    # ── LLM usage stats ────────────────────────────────────────
    if reply.stats:
        _print_stats(reply.stats)

    print(f"\n{reply}\n")


def _print_stats(stats: TurnStats) -> None:
    """Render LLM usage statistics panel for CLI output."""
    lines: list[str] = []
    lines.append("  " + "─" * 50)
    lines.append("  LLM Stats")

    # 主循环调用
    chat_calls = stats.chat_loop_calls
    sub_calls = stats.sub_agent_calls

    def _cache_info(prompt: int, cached: int, missed: int) -> str:
        parts = []
        if cached:
            rate = cached / prompt * 100
            parts.append(f"cache: {cached:,} ({rate:.0f}%)")
        if missed:
            parts.append(f"miss: {missed:,}")
        if parts:
            return "  [" + ", ".join(parts) + "]"
        return ""

    def _missed(usage) -> int:
        return usage.prompt_cache_miss_tokens if usage else 0

    if chat_calls:
        chat_prompt = sum(c.usage.prompt_tokens for c in chat_calls if c.usage)
        chat_comp = sum(c.usage.completion_tokens for c in chat_calls if c.usage)
        chat_cached = sum(c.usage.cached_tokens for c in chat_calls if c.usage)
        chat_missed = sum(_missed(c.usage) for c in chat_calls)
        chat_total = chat_prompt + chat_comp
        chat_dur = sum(c.duration_ms for c in chat_calls)
        lines.append(
            f"    Main loop ({len(chat_calls)} call(s)): "
            f"prompt {chat_prompt:,} + completion {chat_comp:,} = total {chat_total:,} tokens"
            f"{_cache_info(chat_prompt, chat_cached, chat_missed)}"
            f"  |  {chat_dur:.0f}ms"
        )
        for i, c in enumerate(chat_calls):
            u = c.usage
            if not u:
                continue
            prompt_n = u.prompt_tokens
            comp_n = u.completion_tokens
            cached_n = u.cached_tokens
            missed_n = _missed(u)
            lines.append(
                f"      [{i+1}] prompt {prompt_n:,} + completion {comp_n:,} = {prompt_n + comp_n:,} tokens"
                f"{_cache_info(prompt_n, cached_n, missed_n)}"
                f"  |  {c.duration_ms:.0f}ms  [model: {c.model}]"
            )

    if sub_calls:
        sub_prompt = sum(c.usage.prompt_tokens for c in sub_calls if c.usage)
        sub_comp = sum(c.usage.completion_tokens for c in sub_calls if c.usage)
        sub_cached = sum(c.usage.cached_tokens for c in sub_calls if c.usage)
        sub_missed = sum(_missed(c.usage) for c in sub_calls)
        sub_total = sub_prompt + sub_comp
        sub_dur = sum(c.duration_ms for c in sub_calls)
        lines.append(
            f"    Sub-agent ({len(sub_calls)} call(s)): "
            f"prompt {sub_prompt:,} + completion {sub_comp:,} = total {sub_total:,} tokens"
            f"{_cache_info(sub_prompt, sub_cached, sub_missed)}"
            f"  |  {sub_dur:.0f}ms"
        )
        for c in sub_calls:
            u = c.usage
            if not u:
                continue
            prompt_n = u.prompt_tokens
            comp_n = u.completion_tokens
            cached_n = u.cached_tokens
            missed_n = _missed(u)
            lines.append(
                f"      [{c.source}] prompt {prompt_n:,} + completion {comp_n:,} = {prompt_n + comp_n:,} tokens"
                f"{_cache_info(prompt_n, cached_n, missed_n)}"
                f"  |  {c.duration_ms:.0f}ms  [model: {c.model}]"
            )

    # 合计
    lines.append("  " + "─" * 50)
    total_pt = stats.total_prompt_tokens
    total_ct = stats.total_completion_tokens
    total_cached = stats.total_cached_tokens
    total_missed = sum(_missed(c.usage) for c in stats.calls)
    lines.append(
        f"  Total: prompt {total_pt:,} + completion {total_ct:,} = {total_pt + total_ct:,} tokens"
        f"{_cache_info(total_pt, total_cached, total_missed)}"
        f"  |  {stats.total_duration_ms:.0f}ms"
    )
    lines.append("")

    print("\n".join(lines))


def _print_event_stats(event: AgentStreamEvent) -> None:
    """Render LLM usage stats from a DONE ``AgentStreamEvent``.

    Groups calls by source (chat_loop vs sub-agents), shows per-call
    detail, and computes cache hit rate percentage.
    """
    if not event.usage:
        return

    stats = event.stats
    lines: list[str] = []
    lines.append("  " + "─" * 50)
    lines.append("  LLM Stats")

    if stats:
        # ── Group by source ────────────────────────────────────────
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

    print("\n".join(lines))


def main() -> None:
    args = _parse_args()

    if args.single_turn:
        _run_single_turn(args)
        return

    agent = RPGGameAgent(
        session_id=args.session_id,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    asyncio.run(_repl(agent, stream=args.stream))


def _run_single_turn(args: argparse.Namespace) -> None:
    """Single-turn: create agent, send message, print reply, exit."""
    agent = RPGGameAgent(
        session_id=args.session_id,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    reply = asyncio.run(agent.single_turn(args.single_turn))
    print(reply)


if __name__ == "__main__":
    main()
