"""Workspace routes — list and switch workspaces."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from rpg_world.api.deps import reset_all
from rpg_world.rpg_core.settings import settings

router = APIRouter(tags=["workspace"])


@router.get("/workspaces")
def list_workspaces() -> dict:
    """Return all available workspaces."""
    return {"workspaces": settings.list_workspaces()}


@router.get("/workspaces/active")
def get_active_workspace() -> dict:
    """Return the currently active workspace."""
    return {"workspace": settings.active_workspace}


@router.put("/workspaces/active")
def set_active_workspace(body: dict) -> dict:
    """Switch to a different workspace.

    Resets all manager caches and the file watcher so subsequent
    requests read from the new workspace's data directories.
    """
    name = body.get("workspace", "")

    # Validate the workspace name exists
    valid = {w["name"] for w in settings.list_workspaces()}
    if name not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid workspace: {name!r}. Valid options: {sorted(valid)}",
        )

    settings.set_active_workspace(name)
    reset_all()

    return {"status": "switched", "workspace": name}
