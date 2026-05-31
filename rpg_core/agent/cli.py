"""CLI entry point for testing the standalone RPG agent.

Usage::

    uv run python -m rpg_world.agent.cli [--model gpt-4o] [--session-id default]
                                         [--api-key ...] [--base-url ...]

Interactive commands:
  /clear   — reset conversation history
  /reload  — reload RPG context from disk
  /history — print raw history
  /quit    — exit
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rpg_world.rpg_core.agent import RPGGameAgent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG Agent CLI")
    parser.add_argument("--model", default="deepseek-v4-flash", help="OpenAI model name")
    parser.add_argument("--session-id", default="default", help="Session identifier")
    parser.add_argument("--api-key", default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    parser.add_argument("--base-url", default="https://api.deepseek.com", help="OpenAI-compatible base URL")
    parser.add_argument("--max-tokens", type=int, default=None, help="Max tokens per response")
    parser.add_argument("--temperature", type=float, default=None, help="Sampling temperature")
    return parser.parse_args()


async def _repl(agent: RPGGameAgent) -> None:
    print("RPG Agent ready.  Commands: /clear  /reload  /history  /quit")
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

        # ── normal chat ────────────────────────────────────────────
        try:
            reply = await agent.send(text)
        except Exception as exc:
            print(f"[error] {exc}\n")
            continue

        print(f"\n{reply}\n")


def main() -> None:
    args = _parse_args()
    agent = RPGGameAgent(
        session_id=args.session_id,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    asyncio.run(_repl(agent))


if __name__ == "__main__":
    main()
