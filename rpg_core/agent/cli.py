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
from rpg_world.rpg_core.agent.stats_formatter import format_event_stats, format_turn_stats


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
                    print(format_event_stats(event))
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
        print(format_turn_stats(reply.stats))

    print(f"\n{reply}\n")


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
