"""Scene endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from play_api.backends import get_agent_backend
from play_api.routers._locator import require_session_locator


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
    workspace: str = Query(...),
    story_id: int = Query(...),
    session_id: str = Query(...),
) -> PlayScene:
    await require_session_locator(workspace, story_id, session_id)
    scene = await get_agent_backend().get_scene(workspace, story_id, session_id)
    return PlayScene(
        attrs=dict(scene.get("attrs", {})),
        time=str(scene["time"]) if scene.get("time") is not None else None,
        location=str(scene["location"]) if scene.get("location") is not None else None,
        present_characters=list(scene.get("presentCharacters", [])),
        mood=str(scene["mood"]) if scene.get("mood") is not None else None,
    )
