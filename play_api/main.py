"""Play API 应用定义。

Play API 是 Play WebUI 的专用后端接口层。它刻意独立于现有
Dashboard API，避免两个前端后续体验演进时被同一套 HTTP 契约绑定。
当前所有路由仅返回空数据或简单 mock。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from play_api.routers import chat, commands, scene, sessions, workspace


app = FastAPI(title="RPG World Play API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PLAY_API_PREFIX = "/play-api/v1"
app.include_router(workspace.router, prefix=_PLAY_API_PREFIX)
app.include_router(sessions.router, prefix=_PLAY_API_PREFIX)
app.include_router(scene.router, prefix=_PLAY_API_PREFIX)
app.include_router(commands.router, prefix=_PLAY_API_PREFIX)
app.include_router(chat.router, prefix=_PLAY_API_PREFIX)
