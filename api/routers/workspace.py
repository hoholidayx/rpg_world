"""Workspace routes — discover, create, rename, and delete workspaces.

Every data endpoint accepts an explicit *workspace* parameter.  This router
provides workspace discovery and lifecycle management.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException

from rpg_world.api.schemas import WorkspaceNameBody
from rpg_world.rpg_core.utils.path_utils import (
    list_workspaces,
    resolve_workspace_root,
    PACKAGE_ROOT,
)

router = APIRouter(tags=["workspace"])

_DATA_DIR = "data"


def _validate_workspace_name(name: str) -> str:
    """Validate and normalise a workspace name.

    Must not be empty, may contain only printable non-slash characters.
    """
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="workspace name is required")
    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="workspace name must not contain slashes")
    return name


def _workspace_path(name: str) -> Path:
    """Return the absolute filesystem path for a named workspace.

    *name* must be a plain directory name (no ``data/`` prefix, no slashes).
    """
    return (PACKAGE_ROOT / _DATA_DIR / name).resolve()


def _data_root() -> Path:
    """Return the resolved absolute path to ``PACKAGE_ROOT/data/``."""
    return (PACKAGE_ROOT / _DATA_DIR).resolve()


def _ensure_within_data_dir(path: Path) -> None:
    """Raise ``HTTPException(400)`` if *path* is not inside the data directory."""
    root = _data_root()
    try:
        path.resolve().relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="workspace path must be within the data directory",
        )


def _resolve_existing_workspace(workspace: str) -> tuple[str, Path]:
    """Resolve a workspace identifier to ``(plain_name, resolved_path)``.

    Accepts workspace identifiers passed via the URL path (e.g.  ``""`` or
    ``"data/my-world"``).  Strips the ``data/`` prefix if present, validates
    the resulting plain name, resolves the absolute path, and verifies it
    stays within ``PACKAGE_ROOT/data/``.

    Raises ``HTTPException(404)`` if the workspace directory does not exist.
    """
    plain = workspace.removeprefix(f"{_DATA_DIR}/")
    plain = plain.strip()
    if not plain:
        raise HTTPException(status_code=400, detail="cannot operate on root workspace")
    _validate_workspace_name(plain)
    ws_path = _workspace_path(plain)
    _ensure_within_data_dir(ws_path)
    if not ws_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace}' not found")
    return plain, ws_path


@router.get("/workspaces")
def list_all_workspaces() -> dict:
    """Return all available workspaces under rpg_world/data/."""
    return {"workspaces": list_workspaces(PACKAGE_ROOT)}


@router.post("/workspaces")
def create_workspace(body: WorkspaceNameBody) -> dict:
    """Create a new workspace directory under ``data/``.

    Body: ``{"name": "my-world"}``

    The workspace name becomes the directory name.  The full workspace
    identifier will be ``data/my-world``.
    """
    name = _validate_workspace_name(body.name)
    ws_path = _workspace_path(name)
    if ws_path.exists():
        raise HTTPException(status_code=409, detail=f"Workspace '{name}' already exists")
    ws_path.mkdir(parents=True)
    return {"status": "created", "name": f"{_DATA_DIR}/{name}"}


@router.put("/workspaces/{workspace:path}")
def rename_workspace(workspace: str, body: WorkspaceNameBody) -> dict:
    """Rename an existing workspace.

    Body: ``{"name": "new-name"}``
    """
    new_name = _validate_workspace_name(body.name)
    old_plain, old_path = _resolve_existing_workspace(workspace)
    new_path = _workspace_path(new_name)
    _ensure_within_data_dir(new_path)

    if new_path.exists():
        raise HTTPException(status_code=409, detail=f"Workspace '{new_name}' already exists")

    old_path.rename(new_path)
    return {"status": "renamed", "from": f"{_DATA_DIR}/{old_plain}", "to": f"{_DATA_DIR}/{new_name}"}


@router.delete("/workspaces/{workspace:path}")
def delete_workspace(workspace: str) -> dict:
    """Delete a workspace and all its contents.

    This is irreversible — all characters, lorebook entries, sessions,
    and other data under the workspace directory will be permanently deleted.
    """
    plain, ws_path = _resolve_existing_workspace(workspace)

    if ws_path.resolve() == _data_root():
        raise HTTPException(status_code=400, detail="cannot delete root data directory")

    shutil.rmtree(ws_path)
    return {"status": "deleted", "workspace": f"{_DATA_DIR}/{plain}"}
