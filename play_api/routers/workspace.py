"""Workspace mock endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/workspaces", tags=["play-workspaces"])


class PlayWorkspace(BaseModel):
    id: str
    name: str
    description: str | None = None


@router.get("", response_model=list[PlayWorkspace])
async def list_workspaces() -> list[PlayWorkspace]:
    """Return mock workspaces until Play API is wired to runtime data."""
    return [PlayWorkspace(id="default", name="默认工作区", description="Play API mock workspace")]
