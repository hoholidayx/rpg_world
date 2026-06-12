"""Session routes — CRUD for sessions under an explicit workspace."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from rpg_world.rpg_core.session import SessionManager
from rpg_world.rpg_core.utils.path_utils import resolve_api_workspace

router = APIRouter(tags=["session"])


def _require_valid_session_id(session_id: str, field_name: str = "session_id") -> str:
    if not session_id:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    try:
        return SessionManager.validate_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_ws(workspace: str) -> str:
    """Resolve workspace, defaulting to the API default when empty."""
    return resolve_api_workspace(workspace)


@router.get("/workspaces/{workspace:path}/sessions")
def list_sessions(workspace: str) -> dict:
    """Return all session IDs for the given workspace."""
    return {"sessions": SessionManager.list_sessions(_resolve_ws(workspace))}


@router.post("/workspaces/{workspace:path}/sessions")
def create_session(workspace: str, body: dict) -> dict:
    """Create a new session under the given workspace."""
    ws = _resolve_ws(workspace)
    session_id = _require_valid_session_id(body.get("session_id", "").strip())

    try:
        SessionManager.create(ws, session_id)
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Session {session_id!r} already exists",
        )

    return {"status": "created", "session_id": session_id}


@router.delete("/workspaces/{workspace:path}/sessions/{session_id}")
def delete_session(workspace: str, session_id: str) -> dict:
    """Delete a session and all its data."""
    ws = _resolve_ws(workspace)
    session_id = _require_valid_session_id(session_id)
    available = set(SessionManager.list_sessions(ws))
    if session_id not in available:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    SessionManager.delete(ws, session_id)
    from rpg_world.api.deps import _session_managers

    _session_managers.pop((ws, session_id), None)

    return {"status": "deleted", "session_id": session_id}


@router.post("/workspaces/{workspace:path}/sessions/{session_id}/clone")
def clone_session(workspace: str, session_id: str, body: dict) -> dict:
    """Clone a session's data to a new session ID."""
    ws = _resolve_ws(workspace)
    session_id = _require_valid_session_id(session_id)
    target_id = _require_valid_session_id(
        body.get("target_session_id", "").strip(),
        field_name="target_session_id",
    )

    try:
        SessionManager.clone(ws, session_id, target_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Source session {session_id!r} not found",
        )
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Target session {target_id!r} already exists",
        )

    return {"status": "cloned", "source": session_id, "target": target_id}
