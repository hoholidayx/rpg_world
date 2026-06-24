"""Command endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from play_api import agent_client

router = APIRouter(prefix="/commands", tags=["play-commands"])


class PlayCommand(BaseModel):
    name: str
    description: str
    mode: str = "slash"


@router.get("", response_model=list[PlayCommand])
async def list_commands(
    workspace: str = Query(...),
    session_id: str = Query(default="demo_session"),
) -> list[PlayCommand]:
    result = await agent_client.get_agent_client().list_commands(workspace, session_id)
    return [
        PlayCommand(
            name=str(item.get("command", "")),
            description=str(item.get("description", "")),
        )
        for item in result.get("commands", [])
    ]
