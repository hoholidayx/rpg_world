"""FastAPI application for RPG World.

入口只有 ``rpg_world/run.py``（Launcher），FastAPI lifespan 不做任何
渠道初始化。所有渠道（Telegram / CLI）由 Launcher 统一管理。
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rpg_world.api.settings import api_settings
from rpg_world.api.routers import character, chat, lorebook, sessions, status, workspace

# Enable rpg_core logging (add handlers so logs appear regardless of uvicorn config)
for _name in ("rpg_core.watcher", "rpg_core.manager"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.INFO)
    if not _log.handlers:
        _log.addHandler(logging.StreamHandler(sys.stderr))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期——仅处理 API 自身生命周期，不涉及渠道。"""
    yield


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
_API_PREFIX = api_settings.api_prefix
app.include_router(character.router, prefix=_API_PREFIX)
app.include_router(chat.router, prefix=_API_PREFIX)
app.include_router(lorebook.router, prefix=_API_PREFIX)
app.include_router(sessions.router, prefix=_API_PREFIX)
app.include_router(status.router, prefix=_API_PREFIX)
app.include_router(workspace.router, prefix=_API_PREFIX)
