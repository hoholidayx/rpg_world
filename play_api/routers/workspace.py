"""Workspace endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from play_api.backends import get_data_manager_backend


router = APIRouter(prefix="/workspaces", tags=["play-workspaces"])


class PlayWorkspace(BaseModel):
    id: str
    name: str
    description: str | None = None


class PlayStory(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    workspace: str
    title: str
    summary: str | None = None
    story_prompt: str = Field(default="", alias="storyPrompt")
    first_message: str = Field(default="", alias="firstMessage")
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


@router.get("", response_model=list[PlayWorkspace])
async def list_workspaces() -> list[PlayWorkspace]:
    """Return workspaces from the configured data manager backend."""
    return [PlayWorkspace(**item) for item in await get_data_manager_backend().list_workspaces()]


@router.get("/{workspace_id}/stories", response_model=list[PlayStory])
async def list_stories(workspace_id: str) -> list[PlayStory]:
    """Return stories in one workspace."""
    stories = await get_data_manager_backend().list_stories(workspace_id)
    if stories is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return [
        PlayStory(
            id=int(item["id"]),
            workspace=str(item["workspace"]),
            title=str(item["title"]),
            summary=str(item["summary"]) if item.get("summary") is not None else None,
            story_prompt=str(item.get("story_prompt") or ""),
            first_message=str(item.get("first_message") or ""),
            created_at=str(item["created_at"]) if item.get("created_at") is not None else None,
            updated_at=str(item["updated_at"]) if item.get("updated_at") is not None else None,
        )
        for item in stories
    ]
