"""Play API 应用定义。

Play API 是 Play WebUI 的专用后端接口层。聊天相关接口通过
Agent 服务后端，数据管理接口通过 rpg_data 后端。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from play_api.runtime import PlayServiceRuntime
from play_api.settings import play_settings
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
    runtime = await PlayServiceRuntime.create(settings=play_settings)
    try:
        app.state.play_runtime = runtime
        app.state.play_events = runtime.events
        app.state.play_data = runtime.data
        yield
    finally:
        try:
            await runtime.close()
        finally:
            if hasattr(app.state, "play_runtime"):
                del app.state.play_runtime
            if hasattr(app.state, "play_events"):
                del app.state.play_events
            if hasattr(app.state, "play_data"):
                del app.state.play_data


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
