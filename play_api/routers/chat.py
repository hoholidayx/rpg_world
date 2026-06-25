"""Chat endpoints for Play WebUI."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from play_api.backends import get_agent_backend
from play_api.routers._locator import require_session_locator

router = APIRouter(prefix="/chat", tags=["play-chat"])


class PlayChatRequest(BaseModel):
    workspace: str
    story_id: int
    session_id: str
    text: str
    mode: str = "ic"


@router.post("/turn")
async def create_turn(payload: PlayChatRequest) -> dict[str, object]:
    await require_session_locator(payload.workspace, payload.story_id, payload.session_id)
    result = await get_agent_backend().send(
        payload.workspace,
        payload.story_id,
        payload.session_id,
        payload.text,
        payload.mode,
    )
    return {
        "turnId": f"turn_{payload.session_id}",
        "status": "completed",
        "workspace": payload.workspace,
        "storyId": payload.story_id,
        "mode": payload.mode,
        "reply": result.get("reply", ""),
        "agent": result,
    }


@router.post("/stream")
async def stream_turn(payload: PlayChatRequest) -> StreamingResponse:
    await require_session_locator(payload.workspace, payload.story_id, payload.session_id)

    async def event_generator():
        async for event in get_agent_backend().stream(
            payload.workspace,
            payload.story_id,
            payload.session_id,
            payload.text,
            payload.mode,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
