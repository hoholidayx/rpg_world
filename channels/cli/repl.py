"""CLI 独立入口 —— 不依赖 API / Telegram，直接启动 CLIAdapter。

用于开发调试或纯终端交互场景。

用法::

    uv run python -m rpg_world.channels.cli.repl [--model gpt-4o]
"""

from __future__ import annotations

import argparse
import asyncio

from rpg_world.channels.cli import CLIAdapter
from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.settings import settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG World CLI（独立模式）")
    parser.add_argument("--model", default=None, help="LLM 模型名")
    parser.add_argument("--session-id", default="default", help="会话 ID")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--base-url", default=None, help="API base URL")
    parser.add_argument("--no-stream", action="store_true", help="禁用流式输出")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()

    agent = RPGGameAgent(
        session_id=args.session_id,
        model=args.model or settings.agent_model,
        api_key=args.api_key,
        base_url=args.base_url or settings.agent_base_url or None,
        max_tokens=settings.agent_max_tokens,
        temperature=settings.agent_temperature,
    )

    adapter = CLIAdapter(agent=agent, streaming=not args.no_stream)
    await adapter.start()


if __name__ == "__main__":
    asyncio.run(_main())
