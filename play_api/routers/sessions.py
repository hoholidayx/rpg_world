"""Session endpoints for Play WebUI."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from play_api.backends import get_agent_backend, get_data_manager_backend
from play_api.routers._locator import require_session_locator

router = APIRouter(prefix="/sessions", tags=["play-sessions"])


class PlaySessionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace: str
    story_id: int = Field(alias="storyId")
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
async def list_sessions(
    workspace: str = Query(...),
    story_id: int = Query(...),
) -> list[PlaySessionSummary]:
    now = datetime.now(UTC).isoformat()
    sessions = await get_data_manager_backend().list_sessions(workspace, story_id)
    if sessions is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [
        PlaySessionSummary(
            id=str(session["id"]),
            workspace=str(session.get("workspace", workspace)),
            story_id=int(session.get("story_id", story_id)),
            title=str(session["title"]) if session.get("title") is not None else None,
            description=str(session["description"]) if session.get("description") is not None else None,
            created_at=str(session.get("created_at") or now),
            updated_at=str(session.get("updated_at") or now),
        )
        for session in sessions
    ]


@router.get("/{session_id}/history", response_model=list[PlayTurn])
async def get_session_history(
    session_id: str,
    workspace: str = Query(...),
    story_id: int = Query(...),
) -> list[PlayTurn]:
    await require_session_locator(workspace, story_id, session_id)
    now = datetime.now(UTC).isoformat()
    turns: list[PlayTurn] = []
    pending_user: str | None = None
    turn_id = 1
    for message in await get_agent_backend().get_history(workspace, story_id, session_id):
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
