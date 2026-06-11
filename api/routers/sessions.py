"""Session routes — CRUD for sessions within the active workspace."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from rpg_world.rpg_core.session import SessionManager

router = APIRouter(tags=["session"])


def _require_valid_session_id(session_id: str, field_name: str = "session_id") -> str:
    if not session_id:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    try:
        return SessionManager.validate_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workspaces/active/sessions")
def list_sessions() -> dict:
    """Return all session IDs for the active workspace."""
    return {"sessions": SessionManager.list_sessions()}


@router.post("/workspaces/active/sessions")
def create_session(body: dict) -> dict:
    """Create a new session.

    The session directory is created under ``sessions/{session_id}/``.
    No data is populated — the session starts empty.
    """
    session_id = _require_valid_session_id(body.get("session_id", "").strip())

    try:
        SessionManager.create(session_id)
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Session {session_id!r} already exists",
        )

    return {"status": "created", "session_id": session_id}


@router.delete("/workspaces/active/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """Delete a session and all its data."""
    session_id = _require_valid_session_id(session_id)
    available = set(SessionManager.list_sessions())
    if session_id not in available:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    SessionManager.delete(session_id)
    # Clear cached manager if any
    from rpg_world.api.deps import _session_managers

    _session_managers.pop(session_id, None)

    return {"status": "deleted", "session_id": session_id}


@router.post("/workspaces/active/sessions/{session_id}/clone")
def clone_session(session_id: str, body: dict) -> dict:
    """Clone a session's data to a new session ID."""
    session_id = _require_valid_session_id(session_id)
    target_id = _require_valid_session_id(
        body.get("target_session_id", "").strip(),
        field_name="target_session_id",
    )

    src_dir = settings.session_dir(session_id)
    dst_dir = settings.session_dir(target_id)

    if not src_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source session {session_id!r} not found",
        )
    if dst_dir.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Target session {target_id!r} already exists",
        )

    try:
        SessionManager.clone(session_id, target_id)
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Target session {target_id!r} already exists",
        )

    return {"status": "cloned", "source": session_id, "target": target_id}
