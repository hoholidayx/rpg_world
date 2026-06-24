"""Scene mock endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field


router = APIRouter(prefix="/scene", tags=["play-scene"])


class PlayScene(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

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
    return PlayScene(
        attrs={"状态": "mock", "workspace": workspace, "session_id": session_id},
        time="未知时间",
        location="未设定地点",
        present_characters=[],
        mood="待展开",
    )
