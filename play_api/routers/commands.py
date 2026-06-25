"""Command endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from play_api.backends import get_agent_backend

router = APIRouter(prefix="/commands", tags=["play-commands"])


class PlayCommand(BaseModel):
    name: str
    description: str
    mode: str = "slash"


@router.get("", response_model=list[PlayCommand])
async def list_commands(
    workspace: str = Query(default="demo_workspace"),
    session_id: str = Query(default="demo_session"),
) -> list[PlayCommand]:
    return [
        PlayCommand(
            name=str(item.get("name", "")),
            description=str(item.get("description", "")),
            mode=str(item.get("mode", "slash")),
        )
        for item in await get_agent_backend().list_commands(workspace, session_id)
    ]
