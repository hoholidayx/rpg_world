"""Workspace endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from play_api.backends import get_data_manager_backend


router = APIRouter(prefix="/workspaces", tags=["play-workspaces"])


class PlayWorkspace(BaseModel):
    id: str
    name: str
    description: str | None = None


@router.get("", response_model=list[PlayWorkspace])
async def list_workspaces() -> list[PlayWorkspace]:
    """Return workspaces from the configured data manager backend."""
    return [PlayWorkspace(**item) for item in await get_data_manager_backend().list_workspaces()]
