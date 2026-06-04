"""CLI entry point for testing the standalone RPG agent.

Usage:

    # Interactive REPL (default)
    uv run python -m rpg_world.agent.cli [--model gpt-4o] [--session-id default] ...

    # Single-turn mode — send one message and exit
    uv run python -m rpg_world.agent.cli --single-turn "look around the room"

Interactive commands:
  /clear   — reset conversation history
  /reload  — reload RPG context from disk
  /history — print raw history
  /context — show current context structure and token usage
  /quit    — exit
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rpg_world.rpg_core.agent import RPGGameAgent
from rpg_world.rpg_core.agent.types import TurnStats


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
    return parser.parse_args()


async def _repl(agent: RPGGameAgent) -> None:
    print("RPG Agent ready.  Commands: /clear  /reload  /history  /context  /quit")
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

        # ── normal chat ────────────────────────────────────────────
        try:
            reply = await agent.send(text)
        except Exception as exc:
            print(f"[error] {exc}\n")
            continue

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

    if chat_calls:
        chat_prompt = sum(c.usage.prompt_tokens for c in chat_calls if c.usage)
        chat_comp = sum(c.usage.completion_tokens for c in chat_calls if c.usage)
        chat_total = chat_prompt + chat_comp
        chat_dur = sum(c.duration_ms for c in chat_calls)
        lines.append(
            f"    Main loop ({len(chat_calls)} call(s)): "
            f"{chat_prompt}p + {chat_comp}c = {chat_total}t  |  {chat_dur:.0f}ms"
        )
        for i, c in enumerate(chat_calls):
            p = c.usage.prompt_tokens if c.usage else 0
            co = c.usage.completion_tokens if c.usage else 0
            cached = c.usage.cached_tokens if c.usage else 0
            suffix = f"  [cache: {cached} hit]" if cached else ""
            lines.append(
                f"      [{i+1}] {p}p + {co}c = {p+co}t  "
                f"|  {c.duration_ms:.0f}ms  [model: {c.model}]{suffix}"
            )

    if sub_calls:
        sub_prompt = sum(c.usage.prompt_tokens for c in sub_calls if c.usage)
        sub_comp = sum(c.usage.completion_tokens for c in sub_calls if c.usage)
        sub_total = sub_prompt + sub_comp
        sub_dur = sum(c.duration_ms for c in sub_calls)
        lines.append(
            f"    Sub-agent ({len(sub_calls)} call(s)): "
            f"{sub_prompt}p + {sub_comp}c = {sub_total}t  |  {sub_dur:.0f}ms"
        )
        for c in sub_calls:
            cached = c.usage.cached_tokens if c.usage else 0
            suffix = f"  [cache: {cached} hit]" if cached else ""
            lines.append(
                f"      [{c.source}] {c.model}{suffix}"
            )

    # 合计
    lines.append("  " + "─" * 50)
    total_pt = stats.total_prompt_tokens
    total_ct = stats.total_completion_tokens
    total_cached = stats.total_cached_tokens
    cache_str = f"  |  cache: {total_cached} hit" if total_cached else ""
    lines.append(
        f"  Total: {total_pt}p + {total_ct}c = {total_pt + total_ct}t"
        f"{cache_str}  |  {stats.total_duration_ms:.0f}ms"
    )
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
    asyncio.run(_repl(agent))


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
