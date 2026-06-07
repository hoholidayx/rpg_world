"""FastAPI application for RPG World."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Enable rpg_core logging (add handlers so logs appear regardless of uvicorn config)
for _name in ("rpg_core.watcher", "rpg_core.manager"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.INFO)
    if not _log.handlers:
        _log.addHandler(logging.StreamHandler(sys.stderr))

from rpg_world.api.routers import character, chat, lorebook, sessions, status, workspace
from rpg_world.channels.config import settings as channels_settings

# ── Launcher 管理标记 ─────────────────────────────────────────────────────
# 由 rpg_world/run.py 设为 True，表示模块生命周期由 launcher 统一管理。
# 当 launcher 未管理时（直接 uvicorn 启动），lifespan 自行管理后台任务。
_launcher_managed: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期。

    当 Launcher（run.py）已启动 Telegram 时，此处不再重复启动。
    如果直接 ``uvicorn api.main:app`` 启动，则自动检测配置并启动 Telegram。
    """
    bg_tasks: list[asyncio.Task] = []

    # 仅在 launcher 未管理时，由 lifespan 自行启动渠道后台任务
    if not _launcher_managed and channels_settings.is_module_enabled("telegram"):
        from rpg_world.rpg_core.agent.manager import AgentManager
        from rpg_world.channels.telegram import TelegramAdapter

        cfg = channels_settings.get_module_config("telegram")
        await AgentManager.ensure_initialized()
        adapter = TelegramAdapter(
            token=cfg["bot_token"],
            streaming=cfg.get("streaming", True),
            agent=AgentManager.get_or_create(),
        )
        task = asyncio.create_task(adapter.start(), name="telegram")
        bg_tasks.append(task)
        logging.getLogger("rpg_world.api").info(
            "Telegram adapter started via lifespan (launcher not managing)",
        )

    yield

    # 关闭后台任务
    for t in bg_tasks:
        t.cancel()
    await asyncio.gather(*bg_tasks, return_exceptions=True)


app = FastAPI(title="RPG World API", lifespan=lifespan)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — each delegates to the corresponding rpg_core module
app.include_router(character.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(lorebook.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(status.router, prefix="/api/v1")
app.include_router(workspace.router, prefix="/api/v1")
