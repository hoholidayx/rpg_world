"""CLI 独立入口。

用于开发调试或纯终端交互场景，不依赖 API / Telegram。

用法::

    uv run python -m rpg_world.channels.cli.repl [--model gpt-4o]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from rpg_world.channels.cli import CLIAdapter
from rpg_world.channels.config import settings as channels_settings
from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.llama_service.client import configure_llama_client_from_memory_settings
from rpg_world.rpg_core.llm.keys import AGENT_MAIN_BIZ_KEY
from rpg_world.rpg_core.llm.manager import LLMManager, ProviderOverrides
from rpg_world.rpg_core.settings import settings
from rpg_world.rpg_core.utils.watcher import get_watcher


def _configure_standard_logging() -> None:
    """Expose stdlib logging used by FileWatcher and memory indexing."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s - %(message)s",
            datefmt="%H:%M:%S",
        )
    root.setLevel(min(root.level, logging.INFO) if root.level else logging.INFO)
    logging.getLogger("rpg_core.watcher").setLevel(logging.INFO)
    logging.getLogger("rpg_world.rpg_core.memory.vector_index_manager").setLevel(logging.INFO)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG World CLI（独立模式）")
    parser.add_argument("--model", default=None, help="LLM 模型名")
    parser.add_argument("--session-id", default=None, help="会话 ID（默认: cli_direct）")
    parser.add_argument("--workspace", default=None, help="工作区标识")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--base-url", default=None, help="API base URL")
    parser.add_argument("--no-stream", action="store_true", help="禁用流式输出")
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    _configure_standard_logging()
    configure_llama_client_from_memory_settings(settings.memory_settings)

    model = args.model or settings.agent_model
    if not model:
        overrides = ProviderOverrides(openai_model=args.model or None) if args.model else None
        model = LLMManager.get().get_provider(AGENT_MAIN_BIZ_KEY, overrides=overrides).get_default_model()

    session_override = (args.session_id or "").strip() or None
    adapter = CLIAdapter(streaming=not args.no_stream, session_id=session_override)
    session_id = adapter.get_initial_session_id()
    agent = RPGGameAgent(
        session_id=session_id,
        workspace=args.workspace or channels_settings.cli_workspace,
        model=model,
        api_key=args.api_key,
        base_url=args.base_url or settings.agent_base_url or None,
        max_tokens=settings.agent_max_tokens,
        temperature=settings.agent_temperature,
    )

    adapter.bind_agent(agent)
    await agent._ensure_initialized()
    watcher = get_watcher()
    if watcher.is_running:
        adapter._console.print(f"[dim]FileWatcher 已启动：session={session_id}[/dim]")
    elif watcher.is_available:
        adapter._console.print(f"[yellow]FileWatcher 未启动：session={session_id}[/yellow]")
    else:
        adapter._console.print("[yellow]FileWatcher 未启用：缺少 watchdog 依赖[/yellow]")
    try:
        await adapter.start()
        return 0
    finally:
        watcher.stop()
        watcher.clear_all()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
