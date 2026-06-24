"""Session mock endpoints for Play WebUI."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field


router = APIRouter(prefix="/sessions", tags=["play-sessions"])


class PlaySessionSummary(BaseModel):
    id: str
    workspace: str
    title: str | None = None
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlayTurn(BaseModel):
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
            id="demo_session",
            workspace=workspace,
            title="演示存档",
            createdAt=now,
            updatedAt=now,
        )
    ]


@router.get("/{session_id}/history", response_model=list[PlayTurn])
async def get_session_history(session_id: str, workspace: str = Query(default="default")) -> list[PlayTurn]:
    _ = (session_id, workspace)
    return []
