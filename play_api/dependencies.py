"""FastAPI dependencies for lifespan-owned Play resources."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from play_api.backends.data_backends import (
    PlayCatalogBackend,
    PlayRuntimeMaintenanceBackend,
    PlaySessionReadBackend,
    PlayStoryAssetBackend,
)
from play_api.data_runtime import PlayDataRuntime


def get_play_data_runtime(request: Request) -> PlayDataRuntime:
    runtime = getattr(request.app.state, "play_data", None)
    if not isinstance(runtime, PlayDataRuntime):
        raise HTTPException(
            status_code=503,
            detail="Play data runtime is not available",
        )
    return runtime


def get_catalog_backend(
    runtime: PlayDataRuntime = Depends(get_play_data_runtime),
) -> PlayCatalogBackend:
    return runtime.catalog


def get_story_asset_backend(
    runtime: PlayDataRuntime = Depends(get_play_data_runtime),
) -> PlayStoryAssetBackend:
    return runtime.story_assets


def get_session_read_backend(
    runtime: PlayDataRuntime = Depends(get_play_data_runtime),
) -> PlaySessionReadBackend:
    return runtime.session_read


def get_runtime_maintenance_backend(
    runtime: PlayDataRuntime = Depends(get_play_data_runtime),
) -> PlayRuntimeMaintenanceBackend:
    return runtime.runtime_maintenance


__all__ = [
    "get_catalog_backend",
    "get_play_data_runtime",
    "get_runtime_maintenance_backend",
    "get_session_read_backend",
    "get_story_asset_backend",
]
