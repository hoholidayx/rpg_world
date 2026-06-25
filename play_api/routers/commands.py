"""Command endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from play_api.backends import get_agent_backend
from play_api.routers._locator import require_session_locator

router = APIRouter(prefix="/commands", tags=["play-commands"])


class PlayCommand(BaseModel):
    name: str
    description: str
    mode: str = "slash"


@router.get("", response_model=list[PlayCommand])
async def list_commands(
    workspace: str = Query(...),
    story_id: int = Query(...),
    session_id: str = Query(...),
) -> list[PlayCommand]:
    await require_session_locator(workspace, story_id, session_id)
    return [
        PlayCommand(
            name=str(item.get("name", "")),
            description=str(item.get("description", "")),
            mode=str(item.get("mode", "slash")),
        )
        for item in await get_agent_backend().list_commands(workspace, story_id, session_id)
    ]
