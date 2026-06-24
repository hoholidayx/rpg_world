"""Command mock endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/commands", tags=["play-commands"])


class PlayCommand(BaseModel):
    name: str
    description: str
    mode: str = "slash"


@router.get("", response_model=list[PlayCommand])
async def list_commands() -> list[PlayCommand]:
    return [
        PlayCommand(name="/continue", description="继续当前剧情"),
        PlayCommand(name="/scene", description="查看当前场景"),
    ]
