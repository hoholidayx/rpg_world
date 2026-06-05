"""Session routes — CRUD for sessions within the active workspace."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from rpg_world.rpg_core.settings import settings

router = APIRouter(tags=["session"])


@router.get("/workspaces/active/sessions")
def list_sessions() -> dict:
    """Return all session IDs for the active workspace."""
    return {"sessions": settings.list_sessions()}


@router.post("/workspaces/active/sessions")
def create_session(body: dict) -> dict:
    """Create a new session.

    The session directory is created under ``sessions/{session_id}/``.
    No data is populated — the session starts empty.
    """
    session_id = body.get("session_id", "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    try:
        settings.create_session(session_id)
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Session {session_id!r} already exists",
        )

    return {"status": "created", "session_id": session_id}


@router.delete("/workspaces/active/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """Delete a session and all its data."""
    available = set(settings.list_sessions())
    if session_id not in available:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    settings.delete_session(session_id)
    # Clear cached manager if any
    from rpg_world.api.deps import _session_managers

    _session_managers.pop(session_id, None)

    return {"status": "deleted", "session_id": session_id}


@router.post("/workspaces/active/sessions/{session_id}/clone")
def clone_session(session_id: str, body: dict) -> dict:
    """Clone a session's data to a new session ID."""
    import shutil

    target_id = body.get("target_session_id", "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="target_session_id is required")

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

    dst_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_dir, dst_dir)

    return {"status": "cloned", "source": session_id, "target": target_id}
