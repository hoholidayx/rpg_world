"""Scene mock endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field


router = APIRouter(prefix="/scene", tags=["play-scene"])


class PlayScene(BaseModel):
    attrs: dict[str, str] = Field(default_factory=dict)
    time: str | None = None
    location: str | None = None
    present_characters: list[str] = Field(default_factory=list, alias="presentCharacters")
    mood: str | None = None


@router.get("/current", response_model=PlayScene)
async def get_current_scene(
    workspace: str = Query(default="default"),
    session_id: str = Query(default="demo_session", alias="sessionId"),
) -> PlayScene:
    _ = (workspace, session_id)
    return PlayScene(
        attrs={"状态": "mock"},
        time="未知时间",
        location="未设定地点",
        presentCharacters=[],
        mood="待展开",
    )
