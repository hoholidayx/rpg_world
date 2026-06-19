"""CLI 独立入口。

用于开发调试或纯终端交互场景，不依赖 API / Telegram。

用法::

    uv run python -m rpg_world.channels.cli.repl [--model gpt-4o]
"""

from __future__ import annotations

import argparse
import asyncio

from rpg_world.channels.cli import CLIAdapter
from rpg_world.channels.config import settings as channels_settings
from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.llama_service.client import configure_llama_client_from_memory_settings
from rpg_world.rpg_core.settings import settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG World CLI（独立模式）")
    parser.add_argument("--model", default=None, help="LLM 模型名")
    parser.add_argument("--session-id", default="default", help="会话 ID")
    parser.add_argument("--workspace", default=None, help="工作区标识")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--base-url", default=None, help="API base URL")
    parser.add_argument("--no-stream", action="store_true", help="禁用流式输出")
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    configure_llama_client_from_memory_settings(settings.memory_settings)

    agent = RPGGameAgent(
        session_id=args.session_id,
        workspace=args.workspace or channels_settings.cli_workspace,
        model=args.model or settings.agent_model,
        api_key=args.api_key,
        base_url=args.base_url or settings.agent_base_url or None,
        max_tokens=settings.agent_max_tokens,
        temperature=settings.agent_temperature,
    )

    adapter = CLIAdapter(agent=agent, streaming=not args.no_stream)
    await adapter.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
