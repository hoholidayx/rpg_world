"""Workspace endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class PlayStoryPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str
    summary: str = ""
    story_prompt: str = Field(default="", alias="storyPrompt")
    first_message: str = Field(default="", alias="firstMessage")

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value


class PlayStoryPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str | None = None
    summary: str | None = None
    story_prompt: str | None = Field(default=None, alias="storyPrompt")
    first_message: str | None = Field(default=None, alias="firstMessage")

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value


def _story_response(item: dict[str, object]) -> PlayStory:
    return PlayStory(
        id=int(item["id"]),
        workspace=str(item["workspace"]),
        title=str(item["title"]),
        summary=str(item["summary"]) if item.get("summary") is not None else None,
        story_prompt=str(item.get("story_prompt") or ""),
        first_message=str(item.get("first_message") or ""),
        created_at=str(item["created_at"]) if item.get("created_at") is not None else None,
        updated_at=str(item["updated_at"]) if item.get("updated_at") is not None else None,
    )


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
    return [_story_response(item) for item in stories]


@router.post("/{workspace_id}/stories", response_model=PlayStory)
async def create_story(workspace_id: str, payload: PlayStoryPayload) -> PlayStory:
    """Create story metadata in one workspace."""
    story = await get_data_manager_backend().create_story(
        workspace_id,
        title=payload.title,
        summary=payload.summary,
        story_prompt=payload.story_prompt,
        first_message=payload.first_message,
    )
    if story is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _story_response(story)


@router.patch("/{workspace_id}/stories/{story_id}", response_model=PlayStory)
async def update_story(
    workspace_id: str,
    story_id: int,
    payload: PlayStoryPatch,
) -> PlayStory:
    """Update story metadata in one workspace."""
    story = await get_data_manager_backend().update_story(
        workspace_id,
        story_id,
        title=payload.title,
        summary=payload.summary,
        story_prompt=payload.story_prompt,
        first_message=payload.first_message,
    )
    if story is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _story_response(story)
