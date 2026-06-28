"""CLI 独立入口。

用于开发调试或纯终端交互场景，通过 Agent 服务交互。

用法::

    uv run python -m channels.cli.repl
"""

from __future__ import annotations

import asyncio
import logging

from agent_service.client import AgentClient
from channels.cli import CLIAdapter
from channels.config import settings as channels_settings


def _logging_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.DEBUG)


def _configure_standard_logging() -> None:
    """Expose stdlib logging used by FileWatcher and memory indexing."""
    log_cfg = channels_settings.logging
    root_level = _logging_level(log_cfg.log_level)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=root_level,
            format="%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s - %(message)s",
            datefmt="%H:%M:%S",
        )
    root.setLevel(root_level)
    logging.getLogger("rpg_core.watcher").setLevel(_logging_level(log_cfg.watcher_log_level))
    logging.getLogger("rp_memory.vector_index_manager").setLevel(_logging_level(log_cfg.vector_index_log_level))


async def main() -> int:
    _configure_standard_logging()
    client = AgentClient()
    session = await client.ensure_session(
        channels_settings.cli_workspace_id,
        channels_settings.cli_story_id,
        session_id=channels_settings.cli_session_id or None,
        title=channels_settings.cli_session_title,
    )
    adapter = CLIAdapter(
        streaming=channels_settings.cli_streaming,
        session_id=str(session["session_id"]),
        workspace=str(session["workspace"]),
        session_title=str(session.get("title") or channels_settings.cli_session_title),
    )
    adapter.bind_agent_client(client)
    await adapter.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
