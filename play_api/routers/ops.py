"""Operational endpoints for maintenance-only Play API actions."""

from __future__ import annotations

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


class OrphanRuntimeItem(BaseModel):
    kind: str
    workspace_id: str = Field(alias="workspaceId")
    story_id: str = Field(alias="storyId")
    session_id: str = Field(alias="sessionId")
    relative_path: str = Field(alias="relativePath")
    path: str


class OrphanRuntimeScanResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    orphan_directories: list[OrphanRuntimeItem] = Field(alias="orphanDirectories")
    unindexed_status_files: list[OrphanRuntimeItem] = Field(alias="unindexedStatusFiles")


def _entry_delete_purpose(workspace_id: str, entry_id: int) -> str:
    return f"ops:lorebook_entry:{workspace_id}:{entry_id}"


def _mount_delete_purpose(workspace_id: str, story_id: int, mount_id: int) -> str:
    return f"ops:lorebook_mount:{workspace_id}:{story_id}:{mount_id}"


def _require_delete_token(token: str | None, purpose: str) -> None:
    if not consume_delete_confirmation_token(token, purpose):
        raise HTTPException(status_code=409, detail="delete confirmation token is required or invalid")


def _scan_item(item: dict[str, str]) -> OrphanRuntimeItem:
    return OrphanRuntimeItem(
        kind=str(item.get("kind", "")),
        workspace_id=str(item.get("workspace_id", "")),
        story_id=str(item.get("story_id", "")),
        session_id=str(item.get("session_id", "")),
        relative_path=str(item.get("relative_path", "")),
        path=str(item.get("path", "")),
    )


@router.get("/orphan-runtime", response_model=OrphanRuntimeScanResponse)
async def scan_orphan_runtime() -> OrphanRuntimeScanResponse:
    scan = await get_data_manager_backend().scan_orphan_runtime()
    return OrphanRuntimeScanResponse(
        orphan_directories=[_scan_item(item) for item in scan.get("orphan_directories", [])],
        unindexed_status_files=[_scan_item(item) for item in scan.get("unindexed_status_files", [])],
    )


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
