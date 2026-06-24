"""Session endpoints for Play WebUI."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from play_api.backend import get_play_backend

router = APIRouter(prefix="/sessions", tags=["play-sessions"])


class PlaySessionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace: str
    title: str | None = None
    description: str | None = None
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlayTurn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    turn_id: int = Field(alias="turnId")
    user_message: str = Field(alias="userMessage")
    assistant_message: str | None = Field(default=None, alias="assistantMessage")
    source: str = "play_webui"
    created_at: str | None = Field(default=None, alias="createdAt")


@router.get("", response_model=list[PlaySessionSummary])
async def list_sessions(workspace: str = Query(default="default")) -> list[PlaySessionSummary]:
    now = datetime.now(UTC).isoformat()
    return [
        PlaySessionSummary(
            id=str(session["id"]),
            workspace=str(session.get("workspace", workspace)),
            title=str(session["title"]) if session.get("title") is not None else None,
            description=str(session["description"]) if session.get("description") is not None else None,
            created_at=now,
            updated_at=now,
        )
        for session in await get_play_backend().list_sessions(workspace)
    ]


@router.get("/{session_id}/history", response_model=list[PlayTurn])
async def get_session_history(
    session_id: str,
    workspace: str = Query(default="default"),
) -> list[PlayTurn]:
    now = datetime.now(UTC).isoformat()
    turns: list[PlayTurn] = []
    pending_user: str | None = None
    turn_id = 1
    for message in await get_play_backend().get_history(workspace, session_id):
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "user":
            pending_user = content
            continue
        if role == "assistant" and pending_user is not None:
            turns.append(
                PlayTurn(
                    turn_id=turn_id,
                    user_message=pending_user,
                    assistant_message=content,
                    created_at=now,
                )
            )
            turn_id += 1
            pending_user = None
    if pending_user is not None:
        turns.append(PlayTurn(turn_id=turn_id, user_message=pending_user, created_at=now))
    return turns
