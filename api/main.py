"""FastAPI application for RPG World."""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Enable rpg_core logging (add handlers so logs appear regardless of uvicorn config)
for _name in ("rpg_core.watcher", "rpg_core.manager"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.INFO)
    if not _log.handlers:
        _log.addHandler(logging.StreamHandler(sys.stderr))

from rpg_world.api.routers import character, context, lorebook, status, workspace

app = FastAPI(title="RPG World API")

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
app.include_router(lorebook.router, prefix="/api/v1")
app.include_router(context.router, prefix="/api/v1")
app.include_router(status.router, prefix="/api/v1")
app.include_router(workspace.router, prefix="/api/v1")
