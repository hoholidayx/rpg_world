"""Character card management endpoints for Play WebUI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from play_api.backends import get_data_manager_backend

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["play-characters"])


class PlayCharacterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    personality: str = ""
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PlayCharacterPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    personality: str | None = None
    content: str | None = None
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


class PlayCharacterDetailPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    sort_order: int = Field(default=0, alias="sortOrder")

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PlayCharacterDetailPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    sort_order: int | None = Field(default=None, alias="sortOrder")

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PlayCharacterDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    character_id: int = Field(alias="characterId")
    name: str
    content: str
    tags: list[str] = Field(default_factory=list)
    sort_order: int = Field(alias="sortOrder")
    version: int
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlayCharacter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    workspace_id: str = Field(alias="workspaceId")
    name: str
    personality: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    details: list[PlayCharacterDetail] = Field(default_factory=list)
    version: int
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    mount_id: int | None = Field(default=None, alias="mountId")
    story_id: int | None = Field(default=None, alias="storyId")


def _detail_response(item: dict[str, object]) -> PlayCharacterDetail:
    return PlayCharacterDetail(
        id=int(item["id"]),
        character_id=int(item["character_id"]),
        name=str(item["name"]),
        content=str(item.get("content") or ""),
        tags=[str(tag) for tag in item.get("tags", []) if isinstance(tag, str)],
        sort_order=int(item.get("sort_order") or 0),
        version=int(item.get("version") or 1),
        created_at=str(item["created_at"]) if item.get("created_at") is not None else None,
        updated_at=str(item["updated_at"]) if item.get("updated_at") is not None else None,
    )


def _character_response(item: dict[str, object]) -> PlayCharacter:
    details = item.get("details", [])
    return PlayCharacter(
        id=int(item["id"]),
        workspace_id=str(item["workspace_id"]),
        name=str(item["name"]),
        personality=str(item.get("personality") or ""),
        content=str(item.get("content") or ""),
        metadata=dict(item.get("metadata") or {}),
        details=[_detail_response(detail) for detail in details if isinstance(detail, dict)],
        version=int(item.get("version") or 1),
        created_at=str(item["created_at"]) if item.get("created_at") is not None else None,
        updated_at=str(item["updated_at"]) if item.get("updated_at") is not None else None,
        mount_id=int(item["mount_id"]) if item.get("mount_id") is not None else None,
        story_id=int(item["story_id"]) if item.get("story_id") is not None else None,
    )


@router.get("/characters", response_model=list[PlayCharacter])
async def list_characters(workspace_id: str) -> list[PlayCharacter]:
    characters = await get_data_manager_backend().list_characters(workspace_id)
    if characters is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return [_character_response(item) for item in characters]


@router.post("/characters", response_model=PlayCharacter)
async def create_character(
    workspace_id: str,
    payload: PlayCharacterPayload,
) -> PlayCharacter:
    character = await get_data_manager_backend().create_character(
        workspace_id,
        name=payload.name,
        personality=payload.personality,
        content=payload.content,
        metadata=payload.metadata,
    )
    if character is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _character_response(character)


@router.patch("/characters/{character_id}", response_model=PlayCharacter)
async def update_character(
    workspace_id: str,
    character_id: int,
    payload: PlayCharacterPatch,
) -> PlayCharacter:
    character = await get_data_manager_backend().update_character(
        workspace_id,
        character_id,
        name=payload.name,
        personality=payload.personality,
        content=payload.content,
        metadata=payload.metadata,
    )
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return _character_response(character)


@router.delete("/characters/{character_id}", status_code=204)
async def delete_character(
    workspace_id: str,
    character_id: int,
) -> None:
    deleted = await get_data_manager_backend().delete_character(workspace_id, character_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="character not found")


@router.post("/characters/{character_id}/details", response_model=PlayCharacterDetail)
async def create_character_detail(
    workspace_id: str,
    character_id: int,
    payload: PlayCharacterDetailPayload,
) -> PlayCharacterDetail:
    detail = await get_data_manager_backend().create_character_detail(
        workspace_id,
        character_id,
        name=payload.name,
        content=payload.content,
        tags=payload.tags,
        sort_order=payload.sort_order,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="character not found")
    return _detail_response(detail)


@router.patch("/characters/{character_id}/details/{detail_id}", response_model=PlayCharacterDetail)
async def update_character_detail(
    workspace_id: str,
    character_id: int,
    detail_id: int,
    payload: PlayCharacterDetailPatch,
) -> PlayCharacterDetail:
    detail = await get_data_manager_backend().update_character_detail(
        workspace_id,
        character_id,
        detail_id,
        name=payload.name,
        content=payload.content,
        tags=payload.tags,
        sort_order=payload.sort_order,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="character detail not found")
    return _detail_response(detail)


@router.delete("/characters/{character_id}/details/{detail_id}", status_code=204)
async def delete_character_detail(
    workspace_id: str,
    character_id: int,
    detail_id: int,
) -> None:
    deleted = await get_data_manager_backend().delete_character_detail(workspace_id, character_id, detail_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="character detail not found")


@router.get("/stories/{story_id}/characters", response_model=list[PlayCharacter])
async def list_story_characters(
    workspace_id: str,
    story_id: int,
) -> list[PlayCharacter]:
    characters = await get_data_manager_backend().list_story_characters(workspace_id, story_id)
    if characters is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [_character_response(item) for item in characters]


@router.post("/stories/{story_id}/characters/{character_id}/mount", response_model=PlayCharacter)
async def mount_character(
    workspace_id: str,
    story_id: int,
    character_id: int,
) -> PlayCharacter:
    character = await get_data_manager_backend().mount_character(workspace_id, story_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="story or character not found")
    return _character_response(character)


@router.delete("/stories/{story_id}/character-mounts/{mount_id}", status_code=204)
async def unmount_character(
    workspace_id: str,
    story_id: int,
    mount_id: int,
) -> None:
    deleted = await get_data_manager_backend().unmount_character(workspace_id, story_id, mount_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    if not deleted:
        raise HTTPException(status_code=404, detail="character mount not found")
