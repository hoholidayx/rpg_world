"""Lorebook management endpoints for Play WebUI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from play_api.backends import get_data_manager_backend

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["play-lorebook"])


class PlayLorebookEntryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    content: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PlayLorebookEntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    content: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PlayLorebookEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    workspace_id: str = Field(alias="workspaceId")
    name: str
    content: str
    description: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    mount_id: int | None = Field(default=None, alias="mountId")
    story_id: int | None = Field(default=None, alias="storyId")


def _entry_response(item: dict[str, object]) -> PlayLorebookEntry:
    return PlayLorebookEntry(
        id=int(item["id"]),
        workspace_id=str(item["workspace_id"]),
        name=str(item["name"]),
        content=str(item.get("content") or ""),
        description=str(item.get("description") or ""),
        tags=[str(tag) for tag in item.get("tags", []) if isinstance(tag, str)],
        metadata=dict(item.get("metadata") or {}),
        version=int(item.get("version") or 1),
        created_at=str(item["created_at"]) if item.get("created_at") is not None else None,
        updated_at=str(item["updated_at"]) if item.get("updated_at") is not None else None,
        mount_id=int(item["mount_id"]) if item.get("mount_id") is not None else None,
        story_id=int(item["story_id"]) if item.get("story_id") is not None else None,
    )


@router.get("/lorebook-entries", response_model=list[PlayLorebookEntry])
async def list_lorebook_entries(workspace_id: str) -> list[PlayLorebookEntry]:
    entries = await get_data_manager_backend().list_lorebook_entries(workspace_id)
    if entries is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return [_entry_response(item) for item in entries]


@router.post("/lorebook-entries", response_model=PlayLorebookEntry)
async def create_lorebook_entry(
    workspace_id: str,
    payload: PlayLorebookEntryPayload,
) -> PlayLorebookEntry:
    entry = await get_data_manager_backend().create_lorebook_entry(
        workspace_id,
        name=payload.name,
        content=payload.content,
        description=payload.description,
        tags=payload.tags,
        metadata=payload.metadata,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _entry_response(entry)


@router.patch("/lorebook-entries/{entry_id}", response_model=PlayLorebookEntry)
async def update_lorebook_entry(
    workspace_id: str,
    entry_id: int,
    payload: PlayLorebookEntryPatch,
) -> PlayLorebookEntry:
    entry = await get_data_manager_backend().update_lorebook_entry(
        workspace_id,
        entry_id,
        name=payload.name,
        content=payload.content,
        description=payload.description,
        tags=payload.tags,
        metadata=payload.metadata,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="lorebook entry not found")
    return _entry_response(entry)


@router.delete("/lorebook-entries/{entry_id}", status_code=204)
async def delete_lorebook_entry(
    workspace_id: str,
    entry_id: int,
) -> None:
    deleted = await get_data_manager_backend().delete_lorebook_entry(workspace_id, entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="lorebook entry not found")


@router.get("/stories/{story_id}/lorebook-entries", response_model=list[PlayLorebookEntry])
async def list_story_lorebook_entries(
    workspace_id: str,
    story_id: int,
) -> list[PlayLorebookEntry]:
    entries = await get_data_manager_backend().list_story_lorebook_entries(workspace_id, story_id)
    if entries is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [_entry_response(item) for item in entries]


@router.post("/stories/{story_id}/lorebook-entries/{entry_id}/mount", response_model=PlayLorebookEntry)
async def mount_lorebook_entry(
    workspace_id: str,
    story_id: int,
    entry_id: int,
) -> PlayLorebookEntry:
    entry = await get_data_manager_backend().mount_lorebook_entry(workspace_id, story_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="story or lorebook entry not found")
    return _entry_response(entry)


@router.delete("/stories/{story_id}/lorebook-mounts/{mount_id}", status_code=204)
async def unmount_lorebook_entry(
    workspace_id: str,
    story_id: int,
    mount_id: int,
) -> None:
    deleted = await get_data_manager_backend().unmount_lorebook_entry(workspace_id, story_id, mount_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    if not deleted:
        raise HTTPException(status_code=404, detail="lorebook mount not found")
