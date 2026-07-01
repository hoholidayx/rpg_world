"""Operational endpoints for maintenance-only Play API actions."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from play_api.backends import get_data_manager_backend
from play_api.delete_tokens import (
    DELETE_CONFIRMATION_HEADER,
    consume_delete_confirmation_token,
    issue_delete_confirmation_token,
)

router = APIRouter(prefix="/ops", tags=["play-ops"])


class PlayDeleteConfirmationToken(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str
    expires_in_seconds: int = Field(alias="expiresInSeconds")


class UnindexedRuntimeItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    category: str
    kind: str
    workspace_id: str = Field(alias="workspaceId")
    story_id: str = Field(default="", alias="storyId")
    session_id: str = Field(default="", alias="sessionId")
    relative_path: str = Field(default="", alias="relativePath")
    path: str


class UnindexedRuntimeScanResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[UnindexedRuntimeItem]


class UnindexedRuntimeDeleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item: UnindexedRuntimeItem | None = None
    items: list[UnindexedRuntimeItem] = Field(default_factory=list)


def _entry_delete_purpose(workspace_id: str, entry_id: int) -> str:
    return f"ops:lorebook_entry:{workspace_id}:{entry_id}"


def _mount_delete_purpose(workspace_id: str, story_id: int, mount_id: int) -> str:
    return f"ops:lorebook_mount:{workspace_id}:{story_id}:{mount_id}"


def _unindexed_delete_purpose(items: list[UnindexedRuntimeItem]) -> str:
    locators = [_unindexed_item_dict(item) for item in items]
    locators = sorted(_dedupe_unindexed_item_dicts(locators), key=lambda locator: json.dumps(locator, ensure_ascii=False, sort_keys=True))
    return f"ops:unindexed_runtime:{json.dumps(locators, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"


def _require_delete_token(token: str | None, purpose: str) -> None:
    if not consume_delete_confirmation_token(token, purpose):
        raise HTTPException(status_code=409, detail="delete confirmation token is required or invalid")


def _unindexed_scan_item(item: dict[str, str]) -> UnindexedRuntimeItem:
    return UnindexedRuntimeItem(
        category=str(item.get("category", "")),
        kind=str(item.get("kind", "")),
        workspace_id=str(item.get("workspace_id", "")),
        story_id=str(item.get("story_id", "")),
        session_id=str(item.get("session_id", "")),
        relative_path=str(item.get("relative_path", "")),
        path=str(item.get("path", "")),
    )


def _unindexed_item_dict(item: UnindexedRuntimeItem) -> dict[str, str]:
    return {
        "category": item.category,
        "kind": item.kind,
        "workspace_id": item.workspace_id,
        "story_id": item.story_id,
        "session_id": item.session_id,
        "relative_path": item.relative_path,
        "path": item.path,
    }


def _dedupe_unindexed_item_dicts(items: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    keys = ("category", "kind", "workspace_id", "story_id", "session_id", "relative_path", "path")
    for item in items:
        normalized = tuple(str(item.get(key, "")) for key in keys)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
    return deduped


def _request_unindexed_items(request: UnindexedRuntimeDeleteRequest) -> list[UnindexedRuntimeItem]:
    items = request.items or ([request.item] if request.item is not None else [])
    if not items:
        raise HTTPException(status_code=422, detail="at least one unindexed runtime item is required")
    workspace_id = items[0].workspace_id
    if any(item.workspace_id != workspace_id for item in items):
        raise HTTPException(status_code=400, detail="all unindexed runtime items must belong to the same workspace")
    return items


@router.get("/unindexed-runtime", response_model=UnindexedRuntimeScanResponse)
async def scan_unindexed_runtime(workspace_id: str) -> UnindexedRuntimeScanResponse:
    scan = await get_data_manager_backend().scan_unindexed_runtime(workspace_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return UnindexedRuntimeScanResponse(
        items=[_unindexed_scan_item(item) for item in scan.get("items", [])],
    )


@router.post("/unindexed-runtime/delete-token", response_model=PlayDeleteConfirmationToken)
async def create_unindexed_runtime_delete_token(
    request: UnindexedRuntimeDeleteRequest,
) -> PlayDeleteConfirmationToken:
    request_items = _request_unindexed_items(request)
    scan = await get_data_manager_backend().scan_unindexed_runtime(request_items[0].workspace_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    targets = _dedupe_unindexed_item_dicts([_unindexed_item_dict(item) for item in request_items])
    if any(target not in scan.get("items", []) for target in targets):
        raise HTTPException(status_code=404, detail="unindexed runtime item not found")
    issued = issue_delete_confirmation_token(_unindexed_delete_purpose(request_items))
    return PlayDeleteConfirmationToken(token=issued.token, expires_in_seconds=issued.expires_in_seconds)


@router.post("/unindexed-runtime/delete", status_code=204)
async def delete_unindexed_runtime(
    request: UnindexedRuntimeDeleteRequest,
    x_delete_confirm_token: str | None = Header(default=None, alias=DELETE_CONFIRMATION_HEADER),
    confirm_token: str | None = Query(default=None),
) -> None:
    request_items = _request_unindexed_items(request)
    _require_delete_token(x_delete_confirm_token or confirm_token, _unindexed_delete_purpose(request_items))
    targets = _dedupe_unindexed_item_dicts([_unindexed_item_dict(item) for item in request_items])
    deleted = await get_data_manager_backend().delete_unindexed_runtime_items(targets)
    if deleted is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    if not deleted:
        raise HTTPException(status_code=404, detail="unindexed runtime item not found")


@router.post(
    "/workspaces/{workspace_id}/lorebook-entries/{entry_id}/delete-token",
    response_model=PlayDeleteConfirmationToken,
)
async def create_lorebook_entry_delete_token(
    workspace_id: str,
    entry_id: int,
) -> PlayDeleteConfirmationToken:
    entry = await get_data_manager_backend().get_lorebook_entry(workspace_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="lorebook entry not found")
    issued = issue_delete_confirmation_token(_entry_delete_purpose(workspace_id, entry_id))
    return PlayDeleteConfirmationToken(token=issued.token, expires_in_seconds=issued.expires_in_seconds)


@router.delete("/workspaces/{workspace_id}/lorebook-entries/{entry_id}", status_code=204)
async def delete_lorebook_entry(
    workspace_id: str,
    entry_id: int,
    x_delete_confirm_token: str | None = Header(default=None, alias=DELETE_CONFIRMATION_HEADER),
    confirm_token: str | None = Query(default=None),
) -> None:
    _require_delete_token(x_delete_confirm_token or confirm_token, _entry_delete_purpose(workspace_id, entry_id))
    deleted = await get_data_manager_backend().delete_lorebook_entry(workspace_id, entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="lorebook entry not found")


@router.post(
    "/workspaces/{workspace_id}/stories/{story_id}/lorebook-mounts/{mount_id}/delete-token",
    response_model=PlayDeleteConfirmationToken,
)
async def create_lorebook_mount_delete_token(
    workspace_id: str,
    story_id: int,
    mount_id: int,
) -> PlayDeleteConfirmationToken:
    exists = await get_data_manager_backend().get_lorebook_mount(workspace_id, story_id, mount_id)
    if exists is None:
        raise HTTPException(status_code=404, detail="story or lorebook mount not found")
    issued = issue_delete_confirmation_token(_mount_delete_purpose(workspace_id, story_id, mount_id))
    return PlayDeleteConfirmationToken(token=issued.token, expires_in_seconds=issued.expires_in_seconds)


@router.delete("/workspaces/{workspace_id}/stories/{story_id}/lorebook-mounts/{mount_id}", status_code=204)
async def unmount_lorebook_entry(
    workspace_id: str,
    story_id: int,
    mount_id: int,
    x_delete_confirm_token: str | None = Header(default=None, alias=DELETE_CONFIRMATION_HEADER),
    confirm_token: str | None = Query(default=None),
) -> None:
    _require_delete_token(x_delete_confirm_token or confirm_token, _mount_delete_purpose(workspace_id, story_id, mount_id))
    deleted = await get_data_manager_backend().unmount_lorebook_entry(workspace_id, story_id, mount_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    if not deleted:
        raise HTTPException(status_code=404, detail="lorebook mount not found")
