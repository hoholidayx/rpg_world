"""Session mock endpoints for Play WebUI."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field


router = APIRouter(prefix="/sessions", tags=["play-sessions"])


class PlaySessionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace: str
    title: str | None = None
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
            id="demo_session",
            workspace=workspace,
            title="演示存档",
            created_at=now,
            updated_at=now,
        )
    ]


@router.get("/{session_id}/history", response_model=list[PlayTurn])
async def get_session_history(
    session_id: str,
    workspace: str = Query(default="default"),
) -> list[PlayTurn]:
    now = datetime.now(UTC).isoformat()
    return [
        PlayTurn(
            turn_id=1,
            user_message=f"继续 {workspace}/{session_id}",
            assistant_message="Play API mock history",
            created_at=now,
        )
    ]
