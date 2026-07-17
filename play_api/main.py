"""Play API 应用定义。

Play API 是 Play WebUI 的专用后端接口层。聊天相关接口通过
Agent 服务后端，数据管理接口通过 rpg_data 后端。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from play_api.backends import close_data_manager_backend, get_data_manager_backend
from play_api.dream_client import close_dream_client
from play_api.media_client import close_media_client
from play_api.tts_client import close_tts_client
from play_api.settings import play_settings
from play_api.routers import (
    characters,
    dream,
    lorebook,
    main_llm,
    media,
    rp_modules,
    session_composer,
    ops,
    sessions,
    status_tables,
    tts,
    workspace,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    get_data_manager_backend()
    try:
        yield
    finally:
        await close_dream_client()
        await close_media_client()
        await close_tts_client()
        close_data_manager_backend()


app = FastAPI(title="RPG World Play API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PLAY_API_PREFIX = play_settings.service.api_prefix
app.include_router(workspace.router, prefix=_PLAY_API_PREFIX)
app.include_router(characters.router, prefix=_PLAY_API_PREFIX)
app.include_router(dream.router, prefix=_PLAY_API_PREFIX)
app.include_router(lorebook.router, prefix=_PLAY_API_PREFIX)
app.include_router(main_llm.router, prefix=_PLAY_API_PREFIX)
app.include_router(media.router, prefix=_PLAY_API_PREFIX)
app.include_router(rp_modules.router, prefix=_PLAY_API_PREFIX)
app.include_router(session_composer.router, prefix=_PLAY_API_PREFIX)
app.include_router(ops.router, prefix=_PLAY_API_PREFIX)
app.include_router(sessions.router, prefix=_PLAY_API_PREFIX)
app.include_router(status_tables.router, prefix=_PLAY_API_PREFIX)
app.include_router(tts.router, prefix=_PLAY_API_PREFIX)
