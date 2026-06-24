"""Chat endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from play_api import agent_client

router = APIRouter(prefix="/chat", tags=["play-chat"])


class PlayChatRequest(BaseModel):
    workspace: str = "default"
    session_id: str = "demo_session"
    text: str
    mode: str = "ic"


@router.post("/turn")
async def create_turn(payload: PlayChatRequest) -> dict[str, object]:
    result = await agent_client.get_agent_client().send(payload.workspace, payload.session_id, payload.text)
    return {
        "turnId": f"turn_{payload.session_id}",
        "status": "completed",
        "workspace": payload.workspace,
        "mode": payload.mode,
        "reply": result.get("reply", ""),
        "agent": result,
    }


@router.post("/stream")
async def stream_turn(payload: PlayChatRequest) -> StreamingResponse:
    async def event_generator():
        async for event in agent_client.get_agent_client().stream(payload.workspace, payload.session_id, payload.text):
            import json

            yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
