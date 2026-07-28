"""Story-owned character card endpoints for Play WebUI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from commons.types import JsonObject
from play_api.backends import PlayStoryAssetBackend
from play_api.dependencies import get_story_asset_backend
from play_api.routers._data_errors import data_integrity_conflict
from rpg_core.character_tags import normalize_character_detail_tags
from rpg_data.errors import DataIntegrityError

router = APIRouter(
    prefix="/workspaces/{workspace_id}/stories/{story_id}/characters",
    tags=["play-characters"],
)


class PlayCharacterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    sort_order: int = Field(default=0, alias="sortOrder")
    metadata: JsonObject = Field(default_factory=dict)

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
    description: str | None = None
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

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        return list(normalize_character_detail_tags(value))


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
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        return (
            list(normalize_character_detail_tags(value))
            if value is not None
            else None
        )


class PlayCharacterDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    story_character_id: int = Field(alias="storyCharacterId")
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
    story_id: int = Field(alias="storyId")
    name: str
    description: str
    sort_order: int = Field(alias="sortOrder")
    metadata: JsonObject = Field(default_factory=dict)
    details: list[PlayCharacterDetail] = Field(default_factory=list)
    version: int
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


def _detail_response(item: dict[str, object]) -> PlayCharacterDetail:
    return PlayCharacterDetail(
        id=int(item["id"]),
        story_character_id=int(item["story_character_id"]),
        name=str(item["name"]),
        content=str(item.get("content") or ""),
        tags=[str(tag) for tag in item.get("tags", []) if isinstance(tag, str)],
        sort_order=int(item.get("sort_order") or 0),
        version=int(item.get("version") or 1),
        created_at=str(item["created_at"]) if item.get("created_at") is not None else None,
        updated_at=str(item["updated_at"]) if item.get("updated_at") is not None else None,
    )


def _character_response(item: dict[str, object]) -> PlayCharacter:
    raw_details = item.get("details", [])
    return PlayCharacter(
        id=int(item["id"]),
        workspace_id=str(item["workspace_id"]),
        story_id=int(item["story_id"]),
        name=str(item["name"]),
        description=str(item.get("description") or ""),
        sort_order=int(item.get("sort_order") or 0),
        metadata=dict(item.get("metadata") or {}),
        details=[
            _detail_response(detail)
            for detail in raw_details
            if isinstance(detail, dict)
        ],
        version=int(item.get("version") or 1),
        created_at=str(item["created_at"]) if item.get("created_at") is not None else None,
        updated_at=str(item["updated_at"]) if item.get("updated_at") is not None else None,
    )


@router.get("", response_model=list[PlayCharacter])
async def list_characters(
    workspace_id: str,
    story_id: int,
    assets: PlayStoryAssetBackend = Depends(get_story_asset_backend),
) -> list[PlayCharacter]:
    characters = await assets.list_characters(
        workspace_id,
        story_id,
    )
    if characters is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [_character_response(item) for item in characters]


@router.post("", response_model=PlayCharacter)
async def create_character(
    workspace_id: str,
    story_id: int,
    payload: PlayCharacterPayload,
    assets: PlayStoryAssetBackend = Depends(get_story_asset_backend),
) -> PlayCharacter:
    try:
        character = await assets.create_character(
            workspace_id,
            story_id,
            name=payload.name,
            description=payload.description,
            sort_order=payload.sort_order,
            metadata=payload.metadata,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="character.create",
            workspace_id=workspace_id,
            story_id=story_id,
        ) from exc
    if character is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _character_response(character)


@router.patch("/{character_id}", response_model=PlayCharacter)
async def update_character(
    workspace_id: str,
    story_id: int,
    character_id: int,
    payload: PlayCharacterPatch,
    assets: PlayStoryAssetBackend = Depends(get_story_asset_backend),
) -> PlayCharacter:
    try:
        character = await assets.update_character(
            workspace_id,
            story_id,
            character_id,
            name=payload.name,
            description=payload.description,
            sort_order=payload.sort_order,
            metadata=payload.metadata,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="character.update",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=character_id,
        ) from exc
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return _character_response(character)


@router.delete("/{character_id}", status_code=204)
async def delete_character(
    workspace_id: str,
    story_id: int,
    character_id: int,
    assets: PlayStoryAssetBackend = Depends(get_story_asset_backend),
) -> None:
    try:
        deleted = await assets.delete_character(
            workspace_id,
            story_id,
            character_id,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="character.delete",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=character_id,
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="character not found")


@router.post("/{character_id}/details", response_model=PlayCharacterDetail)
async def create_character_detail(
    workspace_id: str,
    story_id: int,
    character_id: int,
    payload: PlayCharacterDetailPayload,
    assets: PlayStoryAssetBackend = Depends(get_story_asset_backend),
) -> PlayCharacterDetail:
    try:
        detail = await assets.create_character_detail(
            workspace_id,
            story_id,
            character_id,
            name=payload.name,
            content=payload.content,
            tags=payload.tags,
            sort_order=payload.sort_order,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="character_detail.create",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=character_id,
        ) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="character not found")
    return _detail_response(detail)


@router.patch("/{character_id}/details/{detail_id}", response_model=PlayCharacterDetail)
async def update_character_detail(
    workspace_id: str,
    story_id: int,
    character_id: int,
    detail_id: int,
    payload: PlayCharacterDetailPatch,
    assets: PlayStoryAssetBackend = Depends(get_story_asset_backend),
) -> PlayCharacterDetail:
    try:
        detail = await assets.update_character_detail(
            workspace_id,
            story_id,
            character_id,
            detail_id,
            name=payload.name,
            content=payload.content,
            tags=payload.tags,
            sort_order=payload.sort_order,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="character_detail.update",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=detail_id,
        ) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="character detail not found")
    return _detail_response(detail)


@router.delete("/{character_id}/details/{detail_id}", status_code=204)
async def delete_character_detail(
    workspace_id: str,
    story_id: int,
    character_id: int,
    detail_id: int,
    assets: PlayStoryAssetBackend = Depends(get_story_asset_backend),
) -> None:
    try:
        deleted = await assets.delete_character_detail(
            workspace_id,
            story_id,
            character_id,
            detail_id,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="character_detail.delete",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=detail_id,
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="character detail not found")
