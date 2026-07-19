"""Workspace endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from play_api.backends import get_data_manager_backend
from rpg_data import models
from rpg_data.story_template import validate_story_text_template


router = APIRouter(prefix="/workspaces", tags=["play-workspaces"])


class PlayWorkspace(BaseModel):
    id: str
    name: str
    description: str | None = None


class PlayStoryOpening(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    title: str
    message: str
    sort_order: int = Field(alias="sortOrder")


class PlayStoryOpeningInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: int | None = Field(default=None, gt=0)
    title: str
    message: str

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("opening title must not be empty")
        return value

    @field_validator("message")
    @classmethod
    def _message_must_be_valid(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("opening message must not be empty")
        validate_story_text_template(value)
        return value

    def to_data_input(self) -> models.StoryOpeningInput:
        return models.StoryOpeningInput(
            id=self.id,
            title=self.title,
            message=self.message,
        )


class PlayStory(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    workspace: str
    title: str
    summary: str | None = None
    story_prompt: str = Field(default="", alias="storyPrompt")
    openings: list[PlayStoryOpening] = Field(default_factory=list)
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlayStoryPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str
    summary: str = ""
    story_prompt: str = Field(default="", alias="storyPrompt")
    openings: list[PlayStoryOpeningInput] = Field(
        default_factory=list,
        max_length=models.MAX_STORY_OPENINGS,
    )

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("story_prompt")
    @classmethod
    def _story_text_template_must_be_valid(cls, value: str) -> str:
        validate_story_text_template(value)
        return value


class PlayStoryPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str | None = None
    summary: str | None = None
    story_prompt: str | None = Field(default=None, alias="storyPrompt")
    openings: list[PlayStoryOpeningInput] | None = Field(
        default=None,
        max_length=models.MAX_STORY_OPENINGS,
    )

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("story_prompt")
    @classmethod
    def _story_text_template_must_be_valid(cls, value: str | None) -> str | None:
        if value is not None:
            validate_story_text_template(value)
        return value


def _story_response(item: dict[str, object]) -> PlayStory:
    return PlayStory(
        id=int(item["id"]),
        workspace=str(item["workspace"]),
        title=str(item["title"]),
        summary=str(item["summary"]) if item.get("summary") is not None else None,
        story_prompt=str(item.get("story_prompt") or ""),
        openings=[PlayStoryOpening.model_validate(opening) for opening in item.get("openings", [])],
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
    try:
        story = await get_data_manager_backend().create_story(
            workspace_id,
            title=payload.title,
            summary=payload.summary,
            story_prompt=payload.story_prompt,
            openings=[opening.to_data_input() for opening in payload.openings],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    try:
        story = await get_data_manager_backend().update_story(
            workspace_id,
            story_id,
            title=payload.title,
            summary=payload.summary,
            story_prompt=payload.story_prompt,
            openings=(
                [opening.to_data_input() for opening in payload.openings]
                if payload.openings is not None
                else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if story is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _story_response(story)
