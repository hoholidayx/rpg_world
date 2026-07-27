"""Story-owned lorebook endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from commons.types import JsonObject
from play_api.backends import get_data_manager_backend
from play_api.routers._data_errors import data_integrity_conflict
from rpg_data.errors import DataIntegrityError

router = APIRouter(
    prefix="/workspaces/{workspace_id}/stories/{story_id}/lorebook-entries",
    tags=["play-lorebook"],
)


class PlayLorebookEntryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    content: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    sort_order: int = Field(default=0, alias="sortOrder")
    metadata: JsonObject = Field(default_factory=dict)

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
    sort_order: int | None = Field(default=None, alias="sortOrder")
    metadata: JsonObject | None = None

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PlayLorebookEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    workspace_id: str = Field(alias="workspaceId")
    story_id: int = Field(alias="storyId")
    name: str
    content: str
    description: str
    tags: list[str] = Field(default_factory=list)
    sort_order: int = Field(alias="sortOrder")
    metadata: JsonObject = Field(default_factory=dict)
    version: int
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


def _entry_response(item: dict[str, object]) -> PlayLorebookEntry:
    return PlayLorebookEntry(
        id=int(item["id"]),
        workspace_id=str(item["workspace_id"]),
        story_id=int(item["story_id"]),
        name=str(item["name"]),
        content=str(item.get("content") or ""),
        description=str(item.get("description") or ""),
        tags=[str(tag) for tag in item.get("tags", []) if isinstance(tag, str)],
        sort_order=int(item.get("sort_order") or 0),
        metadata=dict(item.get("metadata") or {}),
        version=int(item.get("version") or 1),
        created_at=str(item["created_at"]) if item.get("created_at") is not None else None,
        updated_at=str(item["updated_at"]) if item.get("updated_at") is not None else None,
    )


@router.get("", response_model=list[PlayLorebookEntry])
async def list_lorebook_entries(
    workspace_id: str,
    story_id: int,
) -> list[PlayLorebookEntry]:
    entries = await get_data_manager_backend().list_lorebook_entries(
        workspace_id,
        story_id,
    )
    if entries is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [_entry_response(item) for item in entries]


@router.post("", response_model=PlayLorebookEntry)
async def create_lorebook_entry(
    workspace_id: str,
    story_id: int,
    payload: PlayLorebookEntryPayload,
) -> PlayLorebookEntry:
    try:
        entry = await get_data_manager_backend().create_lorebook_entry(
            workspace_id,
            story_id,
            name=payload.name,
            content=payload.content,
            description=payload.description,
            tags=payload.tags,
            sort_order=payload.sort_order,
            metadata=payload.metadata,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="lorebook_entry.create",
            workspace_id=workspace_id,
            story_id=story_id,
        ) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _entry_response(entry)


@router.patch("/{entry_id}", response_model=PlayLorebookEntry)
async def update_lorebook_entry(
    workspace_id: str,
    story_id: int,
    entry_id: int,
    payload: PlayLorebookEntryPatch,
) -> PlayLorebookEntry:
    try:
        entry = await get_data_manager_backend().update_lorebook_entry(
            workspace_id,
            story_id,
            entry_id,
            name=payload.name,
            content=payload.content,
            description=payload.description,
            tags=payload.tags,
            sort_order=payload.sort_order,
            metadata=payload.metadata,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="lorebook_entry.update",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=entry_id,
        ) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="lorebook entry not found")
    return _entry_response(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_lorebook_entry(
    workspace_id: str,
    story_id: int,
    entry_id: int,
) -> None:
    try:
        deleted = await get_data_manager_backend().delete_lorebook_entry(
            workspace_id,
            story_id,
            entry_id,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="lorebook_entry.delete",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=entry_id,
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="lorebook entry not found")
