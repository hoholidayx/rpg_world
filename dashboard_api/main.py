"""Dashboard API application."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard_api.settings import api_settings
from dashboard_api.routers import character, chat, lorebook, sessions, status, workspace


def _logging_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.DEBUG)


# Enable rpg_core logging (add handlers so logs appear regardless of uvicorn config)
_LOG_LEVELS = {
    "rpg_core.watcher": api_settings.logging.watcher_log_level,
    "rpg_core.manager": api_settings.logging.manager_log_level,
}
for _name, _level_name in _LOG_LEVELS.items():
    _log = logging.getLogger(_name)
    _log.setLevel(_logging_level(_level_name))
    if not _log.handlers:
        _log.addHandler(logging.StreamHandler(sys.stderr))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifecycle for Dashboard API resources only."""
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
