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
from commons.process_logging import configure_process_logging


def _logging_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.DEBUG)


def _configure_logging() -> None:
    """Expose stdlib logging used by FileWatcher and memory indexing."""
    log_cfg = channels_settings.logging
    configure_process_logging("cli", log_cfg)
    logging.getLogger("rpg_core.watcher").setLevel(_logging_level(log_cfg.watcher_log_level))
    logging.getLogger("rp_memory.vector_index_manager").setLevel(_logging_level(log_cfg.vector_index_log_level))


async def main() -> int:
    _configure_logging()
    client = AgentClient()
    ensure_kwargs = {}
    if channels_settings.cli_player_character_id > 0:
        ensure_kwargs["player_character_id"] = channels_settings.cli_player_character_id
    session = await client.ensure_session(
        channels_settings.cli_workspace_id,
        channels_settings.cli_story_id,
        session_id=channels_settings.cli_session_id or None,
        title=channels_settings.cli_session_title,
        **ensure_kwargs,
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
