"""Play API 应用定义。

Play API 是 Play WebUI 的专用后端接口层。聊天相关接口通过
Agent 服务后端，数据管理接口通过 rpg_data 后端。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from play_api.backends import close_data_manager_backend, get_data_manager_backend
from play_api.dream_client import close_dream_client
from play_api.media_client import close_media_client
from play_api.tts_client import close_tts_client
from play_api.settings import play_settings
from play_api.event_hub import PlayEventHub, PlayEventRuntime
from play_events.auth import uses_default_play_event_token
from play_api.routers import (
    characters,
    dream,
    events,
    lorebook,
    main_llm,
    media,
    plot_scheduling,
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
    event_cfg = play_settings.events
    if uses_default_play_event_token(event_cfg.token_env):
        logger.warning(
            "{} is not set; using the local Play event token fallback",
            event_cfg.token_env,
        )
    event_hub = PlayEventHub(
        subscriber_queue_capacity=event_cfg.subscriber_queue_capacity,
    )
    app.state.play_events = PlayEventRuntime(
        hub=event_hub,
        token=event_cfg.token,
        heartbeat_seconds=event_cfg.heartbeat_seconds,
        retry_ms=event_cfg.retry_ms,
    )
    try:
        get_data_manager_backend()
        yield
    finally:
        try:
            await event_hub.close()
        finally:
            del app.state.play_events
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
app.include_router(events.router, prefix=_PLAY_API_PREFIX)
app.include_router(lorebook.router, prefix=_PLAY_API_PREFIX)
app.include_router(main_llm.router, prefix=_PLAY_API_PREFIX)
app.include_router(media.router, prefix=_PLAY_API_PREFIX)
app.include_router(plot_scheduling.router, prefix=_PLAY_API_PREFIX)
app.include_router(rp_modules.router, prefix=_PLAY_API_PREFIX)
app.include_router(session_composer.router, prefix=_PLAY_API_PREFIX)
app.include_router(ops.router, prefix=_PLAY_API_PREFIX)
app.include_router(sessions.router, prefix=_PLAY_API_PREFIX)
app.include_router(sessions.derivation_router, prefix=_PLAY_API_PREFIX)
app.include_router(status_tables.router, prefix=_PLAY_API_PREFIX)
app.include_router(tts.router, prefix=_PLAY_API_PREFIX)
