"""Chat mock endpoints for Play WebUI."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


router = APIRouter(prefix="/chat", tags=["play-chat"])


class PlayChatRequest(BaseModel):
    workspace: str = "default"
    session_id: str = "demo_session"
    text: str
    mode: str = "ic"


async def _mock_stream(payload: PlayChatRequest) -> AsyncIterator[str]:
    events = [
        {
            "kind": "round_start",
            "round_index": 1,
            "workspace": payload.workspace,
            "session_id": payload.session_id,
            "mode": payload.mode,
        },
        {"kind": "thinking", "content": "Play API mock 正在构思..."},
        {"kind": "text", "content": f"这是一段来自 Play API mock 的流式剧情：{payload.text}"},
        {"kind": "done", "finish_reason": "mock"},
    ]
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/turn")
async def create_turn(payload: PlayChatRequest) -> dict[str, str]:
    return {
        "turnId": f"mock_turn_{payload.session_id}",
        "status": "accepted",
        "workspace": payload.workspace,
        "mode": payload.mode,
    }


@router.post("/stream")
async def stream_turn(payload: PlayChatRequest) -> StreamingResponse:
    return StreamingResponse(_mock_stream(payload), media_type="text/event-stream")
